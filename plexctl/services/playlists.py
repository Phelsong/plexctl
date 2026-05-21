"""Plex playlist service — regular and smart playlists.

This module provides two services for managing Plex playlists:

- PlaylistService: CRUD and item management for regular (manual) playlists.
- SmartPlaylistService: CRUD and filter management for smart playlists.

Both services use the PlexHTTPClient for direct HTTP API access to the Plex
server, and share common helpers for parsing playlist data from API responses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from plexctl.models import (
    PLAYLIST_TYPE_MAP,
    MediaType,
    Playlist,
    PlaylistItem,
    PlaylistType,
    SmartPlaylist,
    SmartPlaylistFilter,
)

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


# ============================================================
#  Shared parsing helpers
# ============================================================


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_bool(value: Any) -> bool:
    """Safely convert a value to bool.

    Handles Plex API conventions: 1/0, true/false, True/False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes")
    return False


def _safe_str(value: Any) -> str | None:
    """Safely convert a value to str, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    return str(value)


def _parse_playlist(item: dict[str, Any]) -> Playlist:
    """Parse a raw Plex API metadata dict into a Playlist.

    Args:
        item: Raw metadata dict from the Plex API.

    Returns:
        Normalized Playlist model.
    """
    playlist_type = None
    raw_type = item.get("playlistType", "")
    if raw_type:
        try:
            playlist_type = PlaylistType(raw_type)
        except ValueError:
            playlist_type = None

    return Playlist(
        key=str(item.get("ratingKey", item.get("key", ""))),
        title=item.get("title", ""),
        playlist_type=playlist_type,
        smart=_safe_bool(item.get("smart")),
        item_count=_safe_int(item.get("leafCount")) or 0,
        composite=item.get("composite") or None,
        added_at=item.get("addedAt"),
        updated_at=item.get("updatedAt"),
    )


def _parse_smart_playlist(item: dict[str, Any]) -> SmartPlaylist:
    """Parse a raw Plex API metadata dict into a SmartPlaylist.

    Args:
        item: Raw metadata dict from the Plex API.

    Returns:
        Normalized SmartPlaylist model.
    """
    playlist_type = None
    raw_type = item.get("playlistType", "")
    if raw_type:
        try:
            playlist_type = PlaylistType(raw_type)
        except ValueError:
            playlist_type = None

    # Try to parse filters from the content path
    content_path = item.get("content", "") or ""
    filters = _parse_filters_from_url(content_path)

    return SmartPlaylist(
        key=str(item.get("ratingKey", item.get("key", ""))),
        title=item.get("title", ""),
        playlist_type=playlist_type,
        smart=_safe_bool(item.get("smart")),
        item_count=_safe_int(item.get("leafCount")) or 0,
        composite=item.get("composite") or None,
        added_at=item.get("addedAt"),
        updated_at=item.get("updatedAt"),
        filters=filters,
    )


def _parse_playlist_item(item: dict[str, Any]) -> PlaylistItem:
    """Parse a raw Plex API metadata dict into a PlaylistItem.

    Args:
        item: Raw metadata dict from the Plex API.

    Returns:
        Normalized PlaylistItem model.
    """
    media_type = MediaType.from_plex_type(item.get("type", ""))

    return PlaylistItem(
        key=str(item.get("ratingKey", item.get("key", ""))),
        title=item.get("title", ""),
        media_type=media_type,
        year=_safe_int(item.get("year")),
        duration=_safe_int(item.get("duration")),
        thumb=item.get("thumb") or None,
    )


def _build_plex_filter_query(
    filters: list[SmartPlaylistFilter],
    name: str,
    playlist_type: PlaylistType | str,
    section_id: str | int | None = None,
    sort: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Build Plex query string params from filter conditions.

    Plex smart playlist filters use a specific encoding:
    - Simple filters: field=value as separate query params
    - Advanced filters: field=[operator:value] syntax
    - The 'type' param selects video/audio/photo content

    Args:
        filters: List of SmartPlaylistFilter conditions.
        name: Playlist title.
        playlist_type: Content type (video, audio, photo).
        section_id: Optional library section to scope the query.
        sort: Optional sort order (e.g. 'year:desc', 'titleSort:asc').
        limit: Maximum items to include in the playlist.

    Returns:
        Dictionary of query parameters for the Plex API call.

    Raises:
        ValueError: If filters is empty.
    """
    if not filters:
        msg = "At least one filter is required for a smart playlist"
        raise ValueError(msg)

    params: dict[str, Any] = {
        "title": name,
        "type": PLAYLIST_TYPE_MAP.get(str(playlist_type), "1"),
        "limit": str(limit),
    }

    if section_id is not None:
        params["sectionID"] = str(section_id)

    if sort:
        params["sort"] = sort

    for filt in filters:
        if filt.operator == "=" or filt.operator == "is":
            params[filt.field] = filt.value
        else:
            # Advanced filter: Plex uses [fieldOPERATORvalue] syntax
            # e.g. year=[year>=2019], genre=[genre!=Action]
            params[filt.field] = f"[{filt.field}{filt.operator}{filt.value}]"

    return params


def _parse_filters_from_url(url: str) -> list[SmartPlaylistFilter]:
    """Extract filter conditions from a Plex playlist content URL.

    The URL contains query parameters that represent the smart filters.
    We parse these back into SmartPlaylistFilter objects.

    Handles both simple formats (field=value) and advanced formats
    (field=[fieldOPERATORvalue]).

    Args:
        url: The playlist content URL (e.g. '/library/playlists/query?...').

    Returns:
        List of SmartPlaylistFilter parsed from the URL.
    """
    if not url or "?" not in url:
        return []

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    # Keys that are not filter fields (they're structural params)
    structural_keys = frozenset(
        {
            "title",
            "type",
            "limit",
            "sort",
            "sectionID",
            "includeExtras",
            "includeNested",
            "composite",
            "compositeCount",
            "compositeParts",
            "includeChildren",
            "view",
            "offset",
            "containerKey",
            "librarySectionID",
        }
    )

    # Known operators, longest first to avoid partial matches
    operators = [">=", "<=", "!=", "contains", ">", "<", "="]

    filters: list[SmartPlaylistFilter] = []
    for key, values in qs.items():
        if key in structural_keys:
            continue

        for raw_value in values:
            # Check for advanced filter syntax: [fieldOPERATORvalue]
            if raw_value.startswith("[") and raw_value.endswith("]"):
                inner = raw_value[1:-1]
                # Try each operator from longest to shortest
                for op in operators:
                    if op in inner:
                        # The field name is embedded before the operator
                        idx = inner.index(op)
                        field_part = inner[:idx]
                        value_part = inner[idx + len(op) :]
                        if field_part and value_part:
                            filters.append(
                                SmartPlaylistFilter(
                                    field=field_part, operator=op, value=value_part
                                )
                            )
                            break
                else:
                    # No operator found inside brackets, treat as simple
                    filters.append(SmartPlaylistFilter(field=key, operator="=", value=inner))
            else:
                filters.append(SmartPlaylistFilter(field=key, operator="=", value=raw_value))

    return filters


# ============================================================
#  PlaylistService — regular/manual playlists
# ============================================================


class PlaylistService:
    """Service for Plex regular (manual) playlist operations.

    Provides typed, high-level methods for creating, managing, and
    querying regular playlists using the Plex direct HTTP API.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def create_playlist(
        self,
        title: str,
        playlist_type: PlaylistType | str = PlaylistType.VIDEO,
        item_keys: list[str] | None = None,
    ) -> Playlist:
        """Create a new regular (manual) playlist.

        Optionally seeds the playlist with items by adding them
        after creation.

        Args:
            title: Playlist title.
            playlist_type: Content type (video, audio, photo).
            item_keys: Optional list of rating keys to add after creation.

        Returns:
            The newly created Playlist.

        Raises:
            ValueError: If title is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not title:
            msg = "Playlist title is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        type_code = PLAYLIST_TYPE_MAP.get(str(playlist_type), "1")

        params: dict[str, Any] = {"title": title, "type": type_code, "smart": "0"}

        data = http.post("/playlists", params=params)

        playlist: Playlist | None = None
        if data is not None:
            container = data.get("MediaContainer", data)
            raw = container.get("Metadata", {})
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            playlist = _parse_playlist(raw)

        if playlist is None:
            effective_type = (
                PlaylistType(playlist_type) if isinstance(playlist_type, str) else playlist_type
            )
            playlist = Playlist(key="", title=title, playlist_type=effective_type, smart=False)

        # Add items if requested
        if item_keys and playlist.key:
            self.add_items(playlist.key, item_keys)
            # Refresh playlist to get updated item count
            updated = self.get_playlist(playlist.key)
            if updated is not None:
                playlist = updated

        return playlist

    def get_playlist(self, key: str | int) -> Playlist | None:
        """Get detailed metadata for a single playlist.

        Args:
            key: The playlist rating key.

        Returns:
            Playlist if found, None otherwise.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        try:
            data = http.get(f"/playlists/{key_str}")
        except Exception:
            return None

        if data is None:
            return None

        container = data.get("MediaContainer", data)
        raw = container.get("Metadata", {})

        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        if not raw:
            return None

        return _parse_playlist(raw)

    def list_playlists(self, section_id: str | int | None = None) -> list[Playlist]:
        """List all regular (non-smart) playlists.

        Filters out smart playlists, returning only manual playlists.

        Args:
            section_id: Optional section key to filter playlists.

        Returns:
            List of Playlist for each regular playlist found.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        path = "/playlists"

        params: dict[str, Any] = {}
        if section_id is not None:
            params["sectionID"] = str(section_id)

        data = http.get(path, params=params if params else None)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        playlists = [_parse_playlist(item) for item in raw_metadata]

        # Filter to only regular (non-smart) playlists
        playlists = [p for p in playlists if not p.smart]

        return playlists

    def update_playlist(self, key: str | int, title: str | None = None) -> Playlist | None:
        """Update a playlist's title.

        Uses the same PUT pattern as collection updates:
        title.value=X&title.locked=1

        Args:
            key: The playlist rating key.
            title: New title for the playlist (None to keep current).

        Returns:
            Updated Playlist, or None if update failed.
        """
        if title is None:
            return self.get_playlist(str(key))

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        params: dict[str, Any] = {"title.value": title, "title.locked": "1"}

        try:
            http.put(f"/playlists/{key_str}", params=params)
        except Exception as exc:
            logger.warning("Failed to update playlist %s: %s", key_str, exc)
            return None

        return self.get_playlist(key_str)

    def delete_playlist(self, key: str | int) -> None:
        """Delete a playlist permanently.

        Args:
            key: The playlist rating key to delete.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)
        http.delete(f"/playlists/{key_str}")

    def add_items(self, key: str | int, item_keys: list[str]) -> int:
        """Add items to a playlist.

        Uses the same URI-based pattern as adding items to collections:
        server://{machine_id}/com.plexapp.plugins.library/library/metadata/{item_key}

        Args:
            key: The playlist rating key.
            item_keys: List of rating keys to add.

        Returns:
            Number of items added.

        Raises:
            ValueError: If item_keys is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not item_keys:
            msg = "At least one item key is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        # Fetch machine identifier for URI construction
        server_data = http.get("/")
        container = server_data.get("MediaContainer", server_data)
        machine_id = container.get("machineIdentifier", "")

        params: dict[str, Any] = {
            "uri": [
                f"server://{machine_id}/com.plexapp.plugins.library/library/metadata/{item_key}"
                for item_key in item_keys
            ]
        }
        http.put(f"/playlists/{key_str}/items", params=params)

        return len(item_keys)

    def remove_items(self, key: str | int, item_keys: list[str]) -> int:
        """Remove items from a playlist.

        Args:
            key: The playlist rating key.
            item_keys: List of rating keys to remove.

        Returns:
            Number of items removed.

        Raises:
            ValueError: If item_keys is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not item_keys:
            msg = "At least one item key is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        params: dict[str, Any] = {"id": item_keys}
        http.delete(f"/playlists/{key_str}/items", params=params)

        return len(item_keys)

    def get_playlist_items(self, key: str | int, limit: int = 100) -> list[PlaylistItem]:
        """Get the items contained in a playlist.

        Args:
            key: The playlist rating key.
            limit: Maximum number of items to return.

        Returns:
            List of PlaylistItem in the playlist.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        params: dict[str, Any] = {"limit": str(limit)}
        data = http.get(f"/playlists/{key_str}/items", params=params)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        return [_parse_playlist_item(item) for item in raw_metadata]


# ============================================================
#  SmartPlaylistService — smart playlists (filter-based)
# ============================================================


class SmartPlaylistService:
    """Service for Plex smart playlist operations.

    Provides typed, high-level methods for creating, managing, and
    querying smart playlists using the Plex direct HTTP API.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def create_smart_playlist(
        self,
        name: str,
        filters: list[SmartPlaylistFilter],
        playlist_type: PlaylistType | str = PlaylistType.VIDEO,
        section_id: str | int | None = None,
        sort: str | None = None,
        limit: int = 100,
    ) -> SmartPlaylist:
        """Create a new smart playlist with dynamic query filters.

        Args:
            name: Playlist title.
            filters: Filter conditions that define the playlist contents.
            playlist_type: Content type (video, audio, photo).
            section_id: Optional library section to scope the query.
            sort: Optional sort order.
            limit: Maximum items to include.

        Returns:
            The newly created SmartPlaylist.

        Raises:
            ValueError: If name or filters are empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not name:
            msg = "Smart playlist name is required"
            raise ValueError(msg)
        if not filters:
            msg = "At least one filter is required for a smart playlist"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        params = _build_plex_filter_query(
            filters=filters,
            name=name,
            playlist_type=playlist_type,
            section_id=section_id,
            sort=sort,
            limit=limit,
        )

        data = http.post("/playlists/query", params=params)

        if data is not None:
            container = data.get("MediaContainer", data)
            raw = container.get("Metadata", {})
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            return _parse_smart_playlist(raw)

        return SmartPlaylist(
            key="",
            title=name,
            playlist_type=(
                PlaylistType(playlist_type) if isinstance(playlist_type, str) else playlist_type
            ),
            smart=True,
            filters=filters,
        )

    def get_smart_playlist(self, key: str | int) -> SmartPlaylist | None:
        """Get detailed metadata for a single smart playlist.

        Args:
            key: The playlist rating key.

        Returns:
            SmartPlaylist if found, None otherwise.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        try:
            data = http.get(f"/playlists/{key_str}")
        except Exception:
            return None

        if data is None:
            return None

        container = data.get("MediaContainer", data)
        raw = container.get("Metadata", {})

        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        if not raw:
            return None

        return _parse_smart_playlist(raw)

    def list_smart_playlists(self, section_id: str | int | None = None) -> list[SmartPlaylist]:
        """List all smart playlists, optionally filtered by section.

        Args:
            section_id: Optional section key to filter playlists.

        Returns:
            List of SmartPlaylist for each smart playlist found.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        path = "/playlists"

        params: dict[str, Any] = {}
        if section_id is not None:
            params["playlistType"] = "smart"
            params["sectionID"] = str(section_id)

        data = http.get(path, params=params if params else None)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        playlists = [_parse_smart_playlist(item) for item in raw_metadata]

        # Filter to only smart playlists if we didn't filter server-side
        if section_id is None:
            playlists = [p for p in playlists if p.smart]

        return playlists

    def update_smart_playlist(
        self,
        key: str | int,
        name: str | None = None,
        filters: list[SmartPlaylistFilter] | None = None,
        sort: str | None = None,
    ) -> SmartPlaylist | None:
        """Update a smart playlist's title, filters, or sort order.

        Rebuilds the entire query when filters are updated, since
        Plex requires replacing the playlist content on filter changes.

        Args:
            key: The playlist rating key.
            name: New title for the playlist (None to keep current).
            filters: New filter conditions (None to keep current).
            sort: New sort order (None to keep current).

        Returns:
            Updated SmartPlaylist, or None if update failed.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        # First, get the current playlist to preserve unchanged fields
        current = self.get_smart_playlist(key_str)
        if current is None:
            return None

        effective_name = name if name is not None else current.title
        effective_filters = filters if filters is not None else current.filters
        effective_sort = sort if sort is not None else None

        # Build update params — for smart playlists, we update via PUT
        params: dict[str, Any] = {}
        if name is not None:
            params["title"] = effective_name

        # When filters change, we need to rebuild the playlist query
        if filters is not None:
            query_params = _build_plex_filter_query(
                filters=effective_filters,
                name=effective_name,
                playlist_type=current.playlist_type or PlaylistType.VIDEO,
                sort=effective_sort,
            )
            # Merge filter params into the update
            params.update(query_params)

        if not params:
            return current

        try:
            http.put(f"/playlists/{key_str}", params=params)
        except Exception as exc:
            logger.warning("Failed to update smart playlist %s: %s", key_str, exc)
            return None

        return self.get_smart_playlist(key_str)

    def delete_smart_playlist(self, key: str | int) -> None:
        """Delete a smart playlist permanently.

        Args:
            key: The playlist rating key to delete.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)
        http.delete(f"/playlists/{key_str}")

    def get_playlist_items(self, key: str | int, limit: int = 100) -> list[PlaylistItem]:
        """Get the items contained in a smart playlist.

        Args:
            key: The playlist rating key.
            limit: Maximum number of items to return.

        Returns:
            List of PlaylistItem matching the smart playlist filters.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        params: dict[str, Any] = {"limit": str(limit)}
        data = http.get(f"/playlists/{key_str}/items", params=params)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        return [_parse_playlist_item(item) for item in raw_metadata]
