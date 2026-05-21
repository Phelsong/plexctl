"""Media tree navigation service for Plex.

Provides hierarchical browsing of library content:
- Section-level tree (shows in a section)
- Show-level tree (seasons of a show)
- Season-level tree (episodes of a season)

Uses PlexHTTPClient for direct API access to hierarchical data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plexctl.models import MediaTreeItem, MediaType

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


class TreeService:
    """Service for hierarchical media tree navigation.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def resolve_section_key(self, section_ref: str) -> str | None:
        """Resolve a section name or key to a numeric section key.

        Accepts either a numeric section key (e.g. "2") or a case-insensitive
        section title (e.g. "TV Shows", "shows") and returns the numeric key.

        Args:
            section_ref: Section key or name to resolve.

        Returns:
            The numeric section key as a string, or None if not found.
        """
        # If it's already a numeric key, return it directly
        if section_ref.isdigit():
            return section_ref

        from plexctl.services.library import LibraryService

        try:
            library_service = LibraryService(self._client)
            sections = library_service.list_sections()
        except Exception:
            logger.warning("Failed to list sections for resolution")
            return None

        # Try exact match first (case-insensitive)
        for section in sections:
            if section.title.lower() == section_ref.lower():
                return section.key

        # Try partial match (contains)
        for section in sections:
            if section_ref.lower() in section.title.lower():
                return section.key

        # Try matching section type
        type_aliases = {
            "shows": "show",
            "movies": "movie",
            "tv": "show",
            "anime": "show",
            "music": "artist",
            "photos": "photo",
        }
        target_type = type_aliases.get(section_ref.lower())
        if target_type:
            matches = [
                s
                for s in sections
                if s.section_type and s.section_type.value == target_type
            ]
            if len(matches) == 1:
                return matches[0].key

        return None

    def get_section_tree(
        self,
        section_key: str | int,
        media_type: str | None = None,
    ) -> list[MediaTreeItem]:
        """Get top-level items in a library section as a tree.

        Args:
            section_key: Section key to browse.
            media_type: Optional filter - "show", "movie", etc.

        Returns:
            List of MediaTreeItem representing the top-level items.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)
        params: dict[str, Any] = {}
        if media_type:
            type_map = {
                "movie": "1",
                "show": "2",
                "artist": "3",
                "photo": "4",
            }
            params["type"] = type_map.get(media_type.lower(), media_type)

        data = http.get(f"/library/sections/{key}/all", params=params)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        items = [_parse_tree_item(entry) for entry in raw_metadata]

        return items

    def get_show_tree(self, show_key: str | int) -> MediaTreeItem | None:
        """Get the seasons for a show as a tree.

        Args:
            show_key: Rating key of the show.

        Returns:
            MediaTreeItem with seasons as children, or None if not found.
        """
        from plexctl.client import PlexHTTPClient

        key = str(show_key)
        http = PlexHTTPClient(self._client)

        # First get the show metadata
        try:
            show_data = http.get(f"/library/metadata/{key}")
        except Exception:
            return None

        if show_data is None:
            return None

        container = show_data.get("MediaContainer", show_data)
        raw_show = container.get("Metadata", {})

        if isinstance(raw_show, list):
            raw_show = raw_show[0] if raw_show else {}

        show_item = _parse_tree_item(raw_show)

        # Then get children (seasons)
        try:
            children_data = http.get(f"/library/metadata/{key}/children")
        except Exception:
            return show_item

        if children_data is None:
            return show_item

        child_container = children_data.get("MediaContainer", children_data)
        raw_children = child_container.get("Metadata", [])

        if isinstance(raw_children, dict):
            raw_children = [raw_children]

        seasons = [
            _parse_tree_item(
                entry,
                parent_key=key,
                parent_title=show_item.title,
            )
            for entry in raw_children
        ]

        show_item.children = seasons
        return show_item

    def get_season_tree(self, season_key: str | int) -> MediaTreeItem | None:
        """Get the episodes for a season as a tree.

        Args:
            season_key: Rating key of the season.

        Returns:
            MediaTreeItem with episodes as children, or None if not found.
        """
        from plexctl.client import PlexHTTPClient

        key = str(season_key)
        http = PlexHTTPClient(self._client)

        # First get the season metadata
        try:
            season_data = http.get(f"/library/metadata/{key}")
        except Exception:
            return None

        if season_data is None:
            return None

        container = season_data.get("MediaContainer", season_data)
        raw_season = container.get("Metadata", {})

        if isinstance(raw_season, list):
            raw_season = raw_season[0] if raw_season else {}

        parent_title = raw_season.get("parentTitle")
        parent_key_val = raw_season.get("parentRatingKey")
        if parent_key_val is not None:
            parent_key_val = str(parent_key_val)

        season_item = _parse_tree_item(
            raw_season,
            parent_key=parent_key_val,
            parent_title=parent_title,
        )

        # Then get children (episodes)
        try:
            children_data = http.get(f"/library/metadata/{key}/children")
        except Exception:
            return season_item

        if children_data is None:
            return season_item

        child_container = children_data.get("MediaContainer", children_data)
        raw_children = child_container.get("Metadata", [])

        if isinstance(raw_children, dict):
            raw_children = [raw_children]

        episodes = [
            _parse_tree_item(
                entry,
                parent_key=key,
                parent_title=season_item.title,
            )
            for entry in raw_children
        ]

        season_item.children = episodes
        return season_item


# --- Helpers ----------------------------------------------------------------


def _parse_tree_item(
    entry: dict[str, Any],
    parent_key: str | None = None,
    parent_title: str | None = None,
) -> MediaTreeItem:
    """Parse a raw API metadata entry into a MediaTreeItem.

    Args:
        entry: Raw metadata dict from the Plex API.
        parent_key: Optional parent rating key.
        parent_title: Optional parent title.

    Returns:
        Parsed MediaTreeItem.
    """
    media_type = MediaType.from_plex_type(entry.get("type", ""))

    return MediaTreeItem(
        key=str(entry.get("ratingKey", entry.get("key", ""))),
        title=entry.get("title"),
        media_type=media_type,
        year=_safe_int(entry.get("year")),
        leaf_count=_safe_int(entry.get("leafCount")),
        viewed_leaf_count=_safe_int(entry.get("viewedLeafCount")),
        parent_key=parent_key,
        parent_title=parent_title,
    )


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
