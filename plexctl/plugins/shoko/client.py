"""Shoko Server API client with lazy connection.

Provides a typed, error-handled HTTP client for the Shoko Server v3 API.
Authentication uses an API key sent via the 'apikey' header.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from plexctl.plugins.shoko.config import ShokoConfig

_API_PREFIX = "/api/v3"


class ShokoClient:
    """Manages HTTP connection to a Shoko Server.

    Wraps httpx.Client to centralize authentication, error handling,
    and request routing for the Shoko v3 API.

    Args:
        config: Validated ShokoConfig with url and apikey.

    Raises:
        ValueError: If config is missing required fields.
        ConnectionError: If the server cannot be reached.
    """

    def __init__(self, config: ShokoConfig) -> None:
        if not config.is_valid():
            missing = []
            if not config.apikey:
                missing.append("SHOKO_KEY")
            if not config.url:
                missing.append("SHOKO_URL")
            msg = f"Missing required config: {', '.join(missing)}"
            raise ValueError(msg)

        self._config = config
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazily create an authenticated HTTP client on first access.

        Returns:
            Configured httpx.Client instance.

        Raises:
            ConnectionError: If the server is unreachable.
        """
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._config.url,
                headers={"apikey": self._config.apikey},
                timeout=self._config.timeout,
            )
            # Verify connectivity
            try:
                resp = self._client.get(f"{_API_PREFIX}/Init/Version")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                self._client = None
                msg = f"Cannot connect to Shoko at {self._config.url}: {exc}"
                raise ConnectionError(msg) from exc
        return self._client

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an authenticated GET request to the Shoko API.

        Args:
            path: API path relative to /api/v3 (e.g. '/Series/123').
            params: Optional query parameters.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self.client.get(f"{_API_PREFIX}{path}", params=params)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def get_list(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Send a GET request that returns a paginated list.

        Shoko v3 paginated endpoints return {Total, List} shapes.

        Args:
            path: API path relative to /api/v3.
            params: Optional query parameters (pageSize, page, etc.).

        Returns:
            Tuple of (items_list, total_count).
        """
        resp = self.get(path, params)
        return resp.get("List", []), resp.get("Total", 0)

    def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Send an authenticated POST request to the Shoko API.

        Args:
            path: API path relative to /api/v3 (e.g. '/Series/123/TMDB/Show').
            json: Optional JSON body for the request.

        Returns:
            Parsed JSON response, or None if the server returns 204 No Content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self.client.post(f"{_API_PREFIX}{path}", json=json)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        result: dict[str, Any] = resp.json()
        return result

    def delete(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Send an authenticated DELETE request to the Shoko API.

        Args:
            path: API path relative to /api/v3.
            json: Optional JSON body for the request.

        Returns:
            Parsed JSON response, or None if the server returns 204 No Content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self.client.request("DELETE", f"{_API_PREFIX}{path}", json=json)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        result: dict[str, Any] = resp.json()
        return result

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    @property
    def is_connected(self) -> bool:
        """Check if a connection has been established."""
        return self._client is not None

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"ShokoClient({self._config.url!r}, {status})"
