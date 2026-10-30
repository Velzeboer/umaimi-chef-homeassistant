"""Client for the Umaimi Chef server's API (see the API table in the repository's README)."""

from __future__ import annotations

from typing import Any

import aiohttp


class UmamiListError(Exception):
    """The server couldn't be reached or returned an error."""


class UmamiListAuthError(UmamiListError):
    """Wrong email or password, or the session was ended."""


class UmamiListApi:
    """Talks to one UmamiList server as one user."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str | None = None) -> None:
        self._session = session
        self.url = url.rstrip("/")
        self.token = token

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Logs in and keeps the session token. Returns {"token", "user"}."""
        result = await self._request(
            "POST", "/api/auth/login", {"email": email, "password": password, "device": "Home Assistant"}
        )
        self.token = result["token"]
        return result

    async def lists(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/lists")

    async def items(self, list_id: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/api/lists/{list_id}/items")

    async def categories(self, list_id: str) -> dict[str, Any]:
        """{"categories": [...], "remembered": {lowercase name: category id}}"""
        return await self._request("GET", f"/api/lists/{list_id}/categories")

    async def add_item(self, list_id: str, item: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/api/lists/{list_id}/items", item)

    async def edit_item(self, item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Changes only the fields in `changes`; None clears a field."""
        return await self._request("PATCH", f"/api/items/{item_id}", changes)

    async def delete_item(self, item_id: str) -> None:
        await self._request("DELETE", f"/api/items/{item_id}")

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            async with self._session.request(
                method, self.url + path, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 204:
                    return None
                data = await resp.json(content_type=None)
                error = data.get("error") if isinstance(data, dict) else None
                if resp.status == 401:
                    raise UmamiListAuthError(error or "Not logged in")
                if resp.status >= 400:
                    raise UmamiListError(error or f"The server returned HTTP {resp.status}")
                return data
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise UmamiListError(f"Can't reach the Umaimi Chef server: {err}") from err
