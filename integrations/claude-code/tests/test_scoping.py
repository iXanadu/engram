import socket
from unittest.mock import patch

from engram_mcp.scoping import resolve_scope_and_user_id


def test_machine_scope():
    hostname = socket.gethostname().split(".")[0].lower()
    assert resolve_scope_and_user_id("machine") == ("machine", hostname)


def test_machine_scope_is_default():
    result = resolve_scope_and_user_id(None, default_scope="machine")
    hostname = socket.gethostname().split(".")[0].lower()
    assert result == ("machine", hostname)


def test_shared_scope():
    assert resolve_scope_and_user_id("shared") == ("shared", "global")


def test_project_scope():
    with patch("engram_mcp.scoping.os.getcwd", return_value="/Users/test/projects/my-app"):
        assert resolve_scope_and_user_id("project") == ("project", "my-app")


def test_custom_scope_passthrough():
    assert resolve_scope_and_user_id("custom-thing") == ("custom-thing", "custom-thing")


def test_none_scope_uses_default():
    assert resolve_scope_and_user_id(None, default_scope="shared") == ("shared", "global")
