"""Plex server client wrapper.

Provides a thin, typed layer over plexapi.server.PlexServer
with connection management and error handling, plus a direct
HTTP client for endpoints not exposed by plexapi.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from defusedxml.ElementTree import fromstring as _safe_xml_fromstring
from plexapi.server import PlexServer

if TYPE_CHECKING:
    # ET is used only for type annotations; all actual XML parsing uses
    # defusedxml to prevent XML bomb and entity-expansion attacks.
    import xml.etree.ElementTree as ET  # nosec B405

    from plexctl.config import PlexConfig


class PlexClient:
    """Manages the connection to a Plex Media Server.

    Wraps plexapi's PlexServer to centralize connection logic
    and provide clean error messages when the server is unreachable.

    Also provides direct HTTP access via httpx for endpoints that
    plexapi does not expose (sessions, server prefs, etc.).

    Args:
        config: Validated PlexConfig with url and token.

    Raises:
        ValueError: If config is missing required fields.
        ConnectionError: If the server cannot be reached.
    """

    def __init__(self, config: PlexConfig) -> None:
        if not config.is_valid():
            missing = []
            if not config.token:
                missing.append("PLEX_TOKEN")
            if not config.url:
                missing.append("PLEX_URL")
            msg = f"Missing required config: {', '.join(missing)}"
            raise ValueError(msg)

        self._config = config
        self._server: PlexServer | None = None
        self._http_client: httpx.Client | None = None

    @property
    def server(self) -> PlexServer:
        """Lazily connect to the Plex server on first access.

        Returns:
            Connected PlexServer instance.

        Raises:
            ConnectionError: If the server is unreachable.
        """
        if self._server is None:
            try:
                self._server = PlexServer(  # type: ignore[no-untyped-call]
                    self._config.url, self._config.token, timeout=self._config.timeout
                )
            except Exception as exc:
                msg = f"Cannot connect to Plex at {self._config.url}: {exc}"
                raise ConnectionError(msg) from exc
        return self._server

    @property
    def http(self) -> httpx.Client:
        """Lazily create an authenticated HTTP client for direct Plex API access.

        Use this for endpoints that plexapi does not expose (sessions,
        server preferences, butler tasks, etc.).

        Returns:
            Configured httpx.Client with Plex auth headers.

        Raises:
            ConnectionError: If the server is unreachable.
        """
        if self._http_client is None:
            self._http_client = httpx.Client(
                base_url=self._config.url,
                headers={"X-Plex-Token": self._config.token, "Accept": "application/json"},
                timeout=self._config.timeout,
            )
            # Verify connectivity
            try:
                resp = self._http_client.get("/")
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                self._http_client = None
                msg = f"Cannot connect to Plex at {self._config.url}: {exc}"
                raise ConnectionError(msg) from exc
        return self._http_client

    @property
    def is_connected(self) -> bool:
        """Check if a connection has been established."""
        return self._server is not None or self._http_client is not None

    def close(self) -> None:
        """Close the underlying HTTP client if open."""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"PlexClient({self._config.url!r}, {status})"


def _is_xml_content_type(content_type: str) -> bool:
    """Check if a content-type header indicates XML.

    Args:
        content_type: Raw Content-Type header value.

    Returns:
        True if the content type is XML (text/xml or application/xml).
    """
    if not content_type:
        return False
    normalized = content_type.lower().split(";")[0].strip()
    return normalized in ("text/xml", "application/xml")


def _xml_to_dict(element: ET.Element) -> dict[str, Any] | str:
    """Recursively convert an XML element to a JSON-friendly dict.

    Mimics the structure Plex uses when returning JSON:
    - Element attributes become dict keys
    - Child elements become dict keys with their tag as the key
    - Multiple children with the same tag become a list
    - Text content is stored under a '#text' key when the element
      also has attributes or children

    Args:
        element: An XML Element to convert.

    Returns:
        A dict representation of the XML element.
    """
    result: dict[str, Any] = dict(element.attrib)

    # Collect child elements by tag name
    children_by_tag: dict[str, list[Any]] = {}
    for child in element:
        child_value = _xml_to_dict(child)
        children_by_tag.setdefault(child.tag, []).append(child_value)

    for tag, items in children_by_tag.items():
        if len(items) == 1:
            result[tag] = items[0]
        else:
            result[tag] = items

    # Handle text content
    text = (element.text or "").strip()
    if text:
        if result:
            result["#text"] = text
        else:
            return text

    return result


def _parse_xml_response(content: bytes) -> Any:
    """Parse XML response content into a JSON-like dict.

    Args:
        content: Raw XML bytes from the response.

    Returns:
        Parsed dict with the root element's tag as the top-level key.
    """
    root = _safe_xml_fromstring(content)
    return {root.tag: _xml_to_dict(root)}


class PlexHTTPClient:
    """Direct HTTP client for Plex API endpoints not covered by plexapi.

    Provides typed methods for REST endpoints like sessions, rating,
    watch history, server preferences, and butler tasks.

    Automatically handles XML responses from the Plex API by converting
    them to JSON-compatible dicts, since some endpoints return XML even
    when JSON is requested via the Accept header.

    Args:
        client: Connected PlexClient instance (uses its httpx.Client).
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def _parse_response(self, resp: httpx.Response) -> Any:
        """Parse an HTTP response, handling both JSON and XML content types.

        The Plex API may return XML even when Accept: application/json
        is set. This method detects the content type and converts XML
        responses to JSON-compatible dicts.

        Args:
            resp: The httpx response to parse.

        Returns:
            Parsed response as a dict, or None for empty/204 responses.

        Raises:
            ValueError: If the response cannot be parsed as JSON or XML.
        """
        if resp.status_code == 204 or not resp.content:
            return None

        content_type = resp.headers.get("Content-Type", "")

        if _is_xml_content_type(content_type):
            return _parse_xml_response(resp.content)

        return resp.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send an authenticated GET request to the Plex API.

        Args:
            path: API path (e.g. '/status/sessions').
            params: Optional query parameters.

        Returns:
            Parsed JSON response, or None if no content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self._client.http.get(path, params=params)
        resp.raise_for_status()
        return self._parse_response(resp)

    def put(
        self, path: str, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None
    ) -> Any:
        """Send an authenticated PUT request to the Plex API.

        Args:
            path: API path (e.g. '/:/rate').
            params: Optional query parameters.
            data: Optional form data.

        Returns:
            Parsed JSON response, or None if no content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self._client.http.put(path, params=params, data=data)
        resp.raise_for_status()
        return self._parse_response(resp)

    def post(
        self, path: str, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None
    ) -> Any:
        """Send an authenticated POST request to the Plex API.

        Args:
            path: API path.
            params: Optional query parameters.
            data: Optional form data.

        Returns:
            Parsed JSON response, or None if no content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self._client.http.post(path, params=params, data=data)
        resp.raise_for_status()
        return self._parse_response(resp)

    def delete(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Send an authenticated DELETE request to the Plex API.

        Args:
            path: API path (e.g. '/library/metadata/{key}').
            params: Optional query parameters.

        Returns:
            Parsed JSON response, or None if no content.

        Raises:
            httpx.HTTPStatusError: If the server returns a non-2xx status.
        """
        resp = self._client.http.request("DELETE", path, params=params)
        resp.raise_for_status()
        return self._parse_response(resp)
