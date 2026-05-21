"""Library administration service for Plex.

Provides high-level operations for:
- Creating, listing, getting, and deleting library sections
- Managing section locations
- Managing collections (CRUD operations)

Uses PlexHTTPClient for endpoints that plexapi does not expose
and PlexClient.server for operations plexapi already supports.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from rich.progress import track

from plexctl.models import (
    CollectionInfo,
    CollectionMetadata,
    LibraryLocation,
    LibrarySection,
    MediaType,
)

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


class LibraryService:
    """Service for Plex library administration.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    # --- Section CRUD -------------------------------------------------------

    def create_section(
        self,
        name: str,
        section_type: str,
        agent: str,
        location_path: str,
        language: str = "en",
        scanner: str | None = None,
    ) -> LibrarySection:
        """Create a new library section.

        Args:
            name: Section name (e.g. "Movies", "TV Shows").
            section_type: Content type - "movie", "show", "artist",
                "photo", or "book".
            agent: Metadata agent (e.g. "com.plexapp.agents.imdb",
                "com.plexapp.agents.thetvdb").
            location_path: Filesystem path for the section content.
            language: Language for the section (default "en").
            scanner: Scanner to use (auto-detected from type if None).

        Returns:
            The newly created LibrarySection.

        Raises:
            ValueError: If required parameters are empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not name:
            msg = "Section name is required"
            raise ValueError(msg)
        if not section_type:
            msg = "Section type is required"
            raise ValueError(msg)
        if not agent:
            msg = "Metadata agent is required"
            raise ValueError(msg)
        if not location_path:
            msg = "Location path is required"
            raise ValueError(msg)

        # Default scanners by type
        scanner_defaults = {
            "movie": "Plex Movie Scanner",
            "show": "Plex Series Scanner",
            "artist": "Plex Music Scanner",
            "photo": "Plex Photo Scanner",
        }
        effective_scanner = scanner or scanner_defaults.get(section_type, "Plex Movie Scanner")

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        params: dict[str, Any] = {
            "name": name,
            "type": section_type,
            "agent": agent,
            "scanner": effective_scanner,
            "language": language,
            "location": location_path,
        }
        http.post("/library/sections", params=params)

        # Plex doesn't return the section in the POST response, so list and find
        sections = self.list_sections()
        for sect in sections:
            if sect.title == name:
                return sect

        # Fallback: return minimal section from what we know
        return LibrarySection(
            key="",
            title=name,
            section_type=MediaType.from_plex_type(section_type),
            agent=agent,
            scanner=effective_scanner,
            language=language,
        )

    def list_sections(self) -> list[LibrarySection]:
        """List all library sections on the server.

        Returns:
            List of LibrarySection for each section.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        data = http.get("/library/sections")

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_sections = container.get("Directory", [])

        if isinstance(raw_sections, dict):
            raw_sections = [raw_sections]

        sections: list[LibrarySection] = []
        for sect in track(raw_sections, description="Getting..."):
            media_type = MediaType.from_plex_type(sect.get("type", ""))
            sections.append(
                LibrarySection(
                    key=str(sect.get("key", "")),
                    title=sect.get("title", ""),
                    section_type=media_type,
                    agent=sect.get("agent"),
                    scanner=sect.get("scanner"),
                    language=sect.get("language"),
                    count=_safe_int_or(sect.get("totalSize") or sect.get("leafCount")),
                )
            )

        return sections

    @lru_cache(maxsize=1)
    def get_section(self, section_key: str | int) -> LibrarySection | None:
        """Get a single library section by key.

        Args:
            section_key: The section key (numeric ID).

        Returns:
            LibrarySection if found, None otherwise.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)

        try:
            data = http.get(f"/library/sections/{key}")
        except Exception:
            return None

        if data is None:
            return None

        container = data.get("MediaContainer", data)
        raw_dir = container.get("Directory", {})

        if isinstance(raw_dir, list):
            raw_dir = raw_dir[0] if raw_dir else {}

        media_type = MediaType.from_plex_type(raw_dir.get("type", ""))
        return LibrarySection(
            key=str(raw_dir.get("key", key)),
            title=raw_dir.get("title", ""),
            section_type=media_type,
            agent=raw_dir.get("agent"),
            scanner=raw_dir.get("scanner"),
            language=raw_dir.get("language"),
            count=_safe_int_or(raw_dir.get("totalSize") or raw_dir.get("leafCount")),
        )

    def update_section(
        self,
        section_key: str | int,
        name: str | None = None,
        scanner: str | None = None,
        agent: str | None = None,
        language: str | None = None,
        location: str | None = None,
    ) -> LibrarySection | None:
        """Update a library section's settings.

        Only fields that are explicitly provided (not None) will be updated.

        Args:
            section_key: The section key to update.
            name: New section name (None to keep current).
            scanner: New scanner name (None to keep current).
            agent: New metadata agent (None to keep current).
            language: New language code (None to keep current).
            location: New filesystem path (None to keep current).

        Returns:
            Updated LibrarySection, or None if update failed.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)

        # Build update params — only include non-None fields
        params: dict[str, Any] = {}
        if name is not None:
            params["name"] = name
        if scanner is not None:
            params["scanner"] = scanner
        if agent is not None:
            params["agent"] = agent
        if language is not None:
            params["language"] = language
        if location is not None:
            params["location"] = location

        if not params:
            return self.get_section(key)

        try:
            http.put(f"/library/sections/{key}", params=params)
        except Exception as exc:
            logger.warning("Failed to update section %s: %s", key, exc)
            return None

        return self.get_section(key)

    def delete_section(self, section_key: str | int) -> None:
        """Delete a library section.

        Permanently removes the section and all its content metadata.

        Args:
            section_key: The section key to delete.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)
        http.delete(f"/library/sections/{key}")

    def section_locations(self, section_key: str | int) -> list[LibraryLocation]:
        """List filesystem locations for a library section.

        Args:
            section_key: The section key.

        Returns:
            List of LibraryLocation for each path in the section.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)

    # --- Collections --------------------------------------------------------

    def list_collections(self, section_key: str | int | None = None) -> list[CollectionInfo]:
        """List collections, optionally filtered by section.

        Args:
            section_key: Optional section key to filter collections.

        Returns:
            List of CollectionInfo for each collection.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        if section_key is not None:
            # Specific section — fetch directly
            path = f"/library/sections/{section_key}/collections"
            data = http.get(path)
            if data is None:
                return []
            container = data.get("MediaContainer", data)
            raw_metadata = container.get("Metadata", [])
            if isinstance(raw_metadata, dict):
                raw_metadata = [raw_metadata]
            return [
                CollectionInfo(
                    key=str(item.get("ratingKey", item.get("key", ""))),
                    title=item.get("title", ""),
                    smart=_safe_bool(item.get("smart")),
                    content_count=_safe_int_or(item.get("childCount", 0)),
                    section_title=None,
                )
                for item in raw_metadata
            ]

        # No section specified — iterate all sections
        all_collections: list[CollectionInfo] = []
        sections = self.list_sections()
        for section in sections:
            path = f"/library/sections/{section.key}/collections"
            try:
                data = http.get(path)
            except Exception as exc:
                # Some section types (e.g. photo) may not support collections
                logger.debug("Skipping collections for section %s: %s", section.key, exc)
                continue
            if data is None:
                continue
            container = data.get("MediaContainer", data)
            raw_metadata = container.get("Metadata", [])
            if isinstance(raw_metadata, dict):
                raw_metadata = [raw_metadata]
            for item in raw_metadata:
                all_collections.append(
                    CollectionInfo(
                        key=str(item.get("ratingKey", item.get("key", ""))),
                        title=item.get("title", ""),
                        smart=_safe_bool(item.get("smart")),
                        content_count=_safe_int_or(item.get("childCount", 0)),
                        section_title=section.title,
                    )
                )
        return all_collections

    def get_collection(self, collection_key: str | int) -> CollectionMetadata | None:
        """Get detailed metadata for a single collection.

        Args:
            collection_key: The collection rating key.

        Returns:
            CollectionMetadata if found, None otherwise.
        """
        from plexctl.client import PlexHTTPClient

        key = str(collection_key)
        http = PlexHTTPClient(self._client)

        try:
            data = http.get(f"/library/metadata/{key}")
        except Exception:
            return None

        if data is None:
            return None

        container = data.get("MediaContainer", data)
        raw = container.get("Metadata", {})

        if isinstance(raw, list):
            raw = raw[0] if raw else {}

        return CollectionMetadata(
            key=str(raw.get("ratingKey", key)),
            title=raw.get("title", ""),
            smart=_safe_bool(raw.get("smart")),
            content_count=_safe_int_or(raw.get("childCount", 0)),
            section_key=raw.get("librarySectionID"),
            section_title=raw.get("librarySectionTitle"),
            summary=raw.get("summary") or None,
            thumb=raw.get("thumb") or None,
            art=raw.get("art") or None,
            added_at=raw.get("addedAt"),
            updated_at=raw.get("updatedAt"),
        )

    def create_collection(
        self, title: str, section_key: str | int, smart: bool = False
    ) -> CollectionMetadata:
        """Create a new collection in a library section.

        Args:
            title: Collection title.
            section_key: Section key to create the collection in.
            smart: Whether to create a smart collection.

        Returns:
            The newly created CollectionMetadata.

        Raises:
            ValueError: If title or section_key is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not title:
            msg = "Collection title is required"
            raise ValueError(msg)
        if not section_key:
            msg = "Section key is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)
        params: dict[str, Any] = {"title": title, "type": "1" if smart else "0", "sectionId": key}
        data = http.post(f"/library/sections/{key}/collections", params=params)

        if data is not None:
            container = data.get("MediaContainer", data)
            raw = container.get("Metadata", {})
            if isinstance(raw, list):
                raw = raw[0] if raw else {}
            return CollectionMetadata(
                key=str(raw.get("ratingKey", "")),
                title=raw.get("title", title),
                smart=smart,
                content_count=0,
                section_key=key,
            )

        return CollectionMetadata(key="", title=title, smart=smart, section_key=key)

    def update_collection(
        self, collection_key: str | int, title: str | None = None, summary: str | None = None
    ) -> CollectionMetadata | None:
        """Update a collection's metadata.

        Args:
            collection_key: The collection rating key.
            title: New title for the collection (None to keep current).
            summary: New summary/description (None to keep current).

        Returns:
            Updated CollectionMetadata, or None if not found.
        """
        from plexctl.client import PlexHTTPClient

        key = str(collection_key)
        http = PlexHTTPClient(self._client)

        # Build edit parameters
        params: dict[str, Any] = {}
        if title is not None:
            params["title.value"] = title
            params["title.locked"] = "1"
        if summary is not None:
            params["summary.value"] = summary
            params["summary.locked"] = "1"

        if not params:
            return self.get_collection(key)

        try:
            http.put(f"/library/metadata/{key}", params=params)
        except Exception as exc:
            logger.warning("Failed to update collection %s: %s", key, exc)
            return None

        return self.get_collection(key)

    def delete_collection(self, collection_key: str | int) -> None:
        """Delete a collection.

        Permanently removes the collection (does not delete member items).

        Args:
            collection_key: The collection rating key.

        Raises:
            httpx.HTTPStatusError: If the API request fails.
        """
        from plexctl.client import PlexHTTPClient

        key = str(collection_key)
        http = PlexHTTPClient(self._client)
        http.delete(f"/library/metadata/{key}")

    def add_to_collection(
        self, collection_key: str | int, item_keys: list[str]
    ) -> CollectionMetadata | None:
        """Add items to a collection.

        Args:
            collection_key: The ratingKey of the collection.
            item_keys: List of ratingKeys to add to the collection.

        Returns:
            Updated collection metadata, or None if the collection doesn't exist.

        Raises:
            ValueError: If item_keys is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not item_keys:
            msg = "At least one item key is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        key = str(collection_key)
        http = PlexHTTPClient(self._client)

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
        http.put(f"/library/metadata/{key}/items", params=params)

        return self.get_collection(key)

    def remove_from_collection(self, collection_key: str | int, item_keys: list[str]) -> None:
        """Remove items from a collection.

        Args:
            collection_key: The ratingKey of the collection.
            item_keys: List of ratingKeys to remove from the collection.

        Raises:
            ValueError: If item_keys is empty.
            httpx.HTTPStatusError: If the API request fails.
        """
        if not item_keys:
            msg = "At least one item key is required"
            raise ValueError(msg)

        from plexctl.client import PlexHTTPClient

        key = str(collection_key)
        http = PlexHTTPClient(self._client)
        params: dict[str, Any] = {"id": item_keys}
        http.delete(f"/library/metadata/{key}/items", params=params)


# --- Helpers ----------------------------------------------------------------


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_int_or(value: Any, default: int = 0) -> int:
    """Safely convert a value to int, returning default for missing/empty values."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


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
