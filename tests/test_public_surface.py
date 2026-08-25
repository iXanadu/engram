"""PUBLIC-SURFACE-2 — admin credentials are refused on the public surface.

check_namespace_access() short-circuits on is_admin by design, so an admin
token pasted into an externally-hosted surface would carry unrestricted
fleet-wide reach behind one bearer string. The edge already hides /admin;
this is the defence-in-depth layer behind it.
"""
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import server.services.principal_service as ps
from server.config import settings
from tests.test_permissions import _cleanup_principal

PUBLIC_HEADER = "x-engram-public"


@pytest_asyncio.fixture
async def enforced_client(services):
    """require_auth=true, with the public-proxy header name set as in prod."""
    with patch("server.auth.settings") as mock_settings, \
         patch("server.dependencies.settings") as mock_dep_settings:
        mock_settings.require_auth = True
        mock_settings.api_token = ""
        mock_settings.public_proxy_header = PUBLIC_HEADER
        mock_dep_settings.require_auth = True
        mock_dep_settings.api_token = ""
        from server.main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost") as c:
            yield c


@pytest.mark.asyncio
class TestAdminRefusedOnPublicSurface:
    async def test_admin_refused_when_public_header_present(self, enforced_client):
        try:
            _, raw_token = await ps.create_principal(
                name="pubsurf-admin", type="agent", is_admin=True,
            )
            resp = await enforced_client.post(
                "/memory/get",
                json={"namespace": "any-namespace", "key": "anything"},
                headers={
                    "Authorization": f"Bearer {raw_token}",
                    PUBLIC_HEADER: "1",
                },
            )
            assert resp.status_code == 403
            assert "public surface" in resp.json()["detail"].lower()
        finally:
            await _cleanup_principal("pubsurf-admin")

    async def test_admin_still_works_without_the_header(self, enforced_client):
        """Inert until the edge sets the header — today's behaviour preserved."""
        try:
            _, raw_token = await ps.create_principal(
                name="pubsurf-admin-2", type="agent", is_admin=True,
            )
            resp = await enforced_client.post(
                "/memory/get",
                json={"namespace": "any-namespace", "key": "anything"},
                headers={"Authorization": f"Bearer {raw_token}"},
            )
            assert resp.status_code == 200
        finally:
            await _cleanup_principal("pubsurf-admin-2")

    async def test_non_admin_unaffected_by_the_header(self, enforced_client):
        """The refusal targets admin reach, not the public route itself —
        a scoped principal is exactly what should keep working there."""
        try:
            _, raw_token = await ps.create_principal(
                name="pubsurf-scoped", type="agent",
                read_namespaces=["fleet"], write_namespaces=[],
            )
            resp = await enforced_client.post(
                "/memory/get",
                json={"namespace": "fleet", "key": "anything"},
                headers={
                    "Authorization": f"Bearer {raw_token}",
                    PUBLIC_HEADER: "1",
                },
            )
            assert resp.status_code in (200, 404)
        finally:
            await _cleanup_principal("pubsurf-scoped")

    async def test_forging_the_header_only_removes_privilege(self, enforced_client):
        """Safety property that lets the app half ship before the edge half:
        presence of the header can never GRANT anything, so a forged header is
        self-denial rather than escalation."""
        try:
            _, raw_token = await ps.create_principal(
                name="pubsurf-forge", type="agent", is_admin=True,
            )
            forged = await enforced_client.post(
                "/memory/get",
                json={"namespace": "any-namespace", "key": "anything"},
                headers={
                    "Authorization": f"Bearer {raw_token}",
                    PUBLIC_HEADER: "totally-made-up",
                },
            )
            assert forged.status_code == 403
        finally:
            await _cleanup_principal("pubsurf-forge")

    async def test_header_name_is_configurable(self):
        assert settings.public_proxy_header == PUBLIC_HEADER
