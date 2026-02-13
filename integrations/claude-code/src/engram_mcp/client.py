import httpx


class MemoryClient:
    """Async HTTP client for the engram semantic memory REST API."""

    def __init__(self, base_url: str = "http://localhost:8920", api_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self._headers = {}
        if api_token:
            self._headers["Authorization"] = f"Bearer {api_token}"

    async def store(
        self,
        key: str,
        value: str,
        namespace: str,
        scope: str,
        user_id: str,
        tags: str = "",
    ) -> dict:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self.base_url}/memory/set",
                json={
                    "namespace": namespace,
                    "key": key,
                    "value": value,
                    "scope": scope,
                    "user_id": user_id,
                    "tags": tags,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get(
        self,
        key: str,
        namespace: str,
        scope: str,
        user_id: str,
    ) -> dict:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self.base_url}/memory/get",
                json={
                    "namespace": namespace,
                    "key": key,
                    "scope": scope,
                    "user_id": user_id,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def search(
        self,
        query: str,
        namespace: str,
        scope: str,
        user_id: str,
        limit: int = 5,
    ) -> dict:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self.base_url}/memory/search",
                json={
                    "namespace": namespace,
                    "query": query,
                    "scope": scope,
                    "user_id": user_id,
                    "limit": limit,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def forget(
        self,
        key: str,
        namespace: str,
        scope: str,
        user_id: str,
    ) -> dict:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self.base_url}/memory/forget",
                json={
                    "namespace": namespace,
                    "key": key,
                    "scope": scope,
                    "user_id": user_id,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> dict:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(
                f"{self.base_url}/health",
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
