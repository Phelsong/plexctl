"""Advanced search service for Plex.

Provides powerful search capabilities beyond basic title search:
- Search by key (exact match by ratingKey)
- Advanced Lucene-style search with multiple filters
- Search by actor, director, title, year, genre
- Find similar media

Uses PlexHTTPClient for direct API access to search endpoints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plexctl.models import MediaType, SearchResult, SimilarMedia

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)

# Plex media type codes for the type= query parameter
_TYPE_MAP: dict[str, str] = {
    "movie": "1",
    "show": "2",
    "season": "3",
    "episode": "4",
    "artist": "5",
    "album": "6",
    "track": "7",
    "photo": "8",
}

# Plex sort order codes
_SORT_MAP: dict[str, str] = {
    "added": "addedAt:desc",
    "added_asc": "addedAt:asc",
    "title": "titleSort:asc",
    "title_desc": "titleSort:desc",
    "year": "year:desc",
    "year_asc": "year:asc",
    "rating": "audienceRating:desc",
    "rating_asc": "audienceRating:asc",
}


def _parse_search_result(item: dict[str, Any]) -> SearchResult:
    """Parse a raw Plex API metadata dict into a SearchResult.

    Args:
        item: Raw metadata dict from the Plex API.

    Returns:
        Normalized SearchResult model.
    """
    media_type = MediaType.from_plex_type(item.get("type", ""))

    return SearchResult(
        key=str(item.get("ratingKey", item.get("key", ""))),
        title=item.get("title", ""),
        media_type=media_type,
        year=_safe_int(item.get("year")),
        summary=item.get("summary") or None,
        rating=_safe_float(item.get("rating")),
        thumb=item.get("thumb") or None,
        section_key=str(item.get("librarySectionID", "")) or None,
        section_title=item.get("librarySectionTitle") or None,
    )


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class SearchService:
    """Service for advanced Plex search operations.

    Provides typed, high-level methods for searching media using
    the Plex direct HTTP API, enabling searches by actor, director,
    genre, year, and more — beyond what plexapi exposes.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def search_by_key(self, key: str | int) -> SearchResult | None:
        """Find a media item by its rating key.

        Args:
            key: Plex rating key (numeric identifier).

        Returns:
            SearchResult if found, None otherwise.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        try:
            data = http.get(f"/library/metadata/{key_str}")
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

        return _parse_search_result(raw)

    def search_advanced(
        self,
        query: str,
        media_type: str | None = None,
        section: str | int | None = None,
        sort: str | None = None,
        agent: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search with advanced filters using the Plex Hub API.

        Args:
            query: Search query string.
            media_type: Filter by media type ('movie', 'show', etc.).
            section: Limit to a specific section key.
            sort: Sort order ('added', 'title', 'year', 'rating',
                  with optional '_asc' or '_desc' suffix).
            agent: Metadata agent to use for search.
            limit: Maximum number of results to return.

        Returns:
            List of matching SearchResult items.
        """
        if not query:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        params: dict[str, Any] = {"query": query}
        if media_type:
            type_code = _TYPE_MAP.get(media_type.lower(), media_type)
            params["type"] = type_code
        if section is not None:
            params["sectionId"] = str(section)
        if sort:
            params["sort"] = _SORT_MAP.get(sort, sort)
        if agent:
            params["agent"] = agent
        if limit:
            params["limit"] = str(limit)

        data = http.get("/hubs/search", params=params)

        if data is None:
            return []

        results: list[SearchResult] = []
        container = data.get("MediaContainer", data)
        hubs = container.get("Hub", [])

        if isinstance(hubs, dict):
            hubs = [hubs]

        for hub in hubs:
            metadata = hub.get("Metadata", [])
            if isinstance(metadata, dict):
                metadata = [metadata]
            results.extend(_parse_search_result(item) for item in metadata)

        return results

    def search_by_actor(self, actor_name: str, media_type: str = "movie") -> list[SearchResult]:
        """Search for media featuring a specific actor.

        Args:
            actor_name: Name of the actor to search for.
            media_type: Media type filter ('movie' or 'show').

        Returns:
            List of matching SearchResult items.
        """
        if not actor_name:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        type_code = _TYPE_MAP.get(media_type.lower(), "1")
        params: dict[str, Any] = {"type": type_code, "actor": actor_name}

        data = http.get("/library/all", params=params)

        return self._parse_library_response(data)

    def search_by_director(
        self, director_name: str, media_type: str = "movie"
    ) -> list[SearchResult]:
        """Search for media directed by a specific director.

        Args:
            director_name: Name of the director to search for.
            media_type: Media type filter ('movie' or 'show').

        Returns:
            List of matching SearchResult items.
        """
        if not director_name:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        type_code = _TYPE_MAP.get(media_type.lower(), "1")
        params: dict[str, Any] = {"type": type_code, "director": director_name}

        data = http.get("/library/all", params=params)

        return self._parse_library_response(data)

    def search_by_title(
        self, query: str, media_type: str | None = None, section: str | int | None = None
    ) -> list[SearchResult]:
        """Search for media by title.

        Args:
            query: Title search string.
            media_type: Filter by media type ('movie', 'show', etc.).
            section: Limit to a specific section key.

        Returns:
            List of matching SearchResult items.
        """
        if not query:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        params: dict[str, Any] = {"title": query}
        if media_type:
            type_code = _TYPE_MAP.get(media_type.lower(), media_type)
            params["type"] = type_code
        if section is not None:
            params["sectionId"] = str(section)

        path = "/library/all"
        if section is not None:
            path = f"/library/sections/{section}/all"

        data = http.get(path, params=params)

        return self._parse_library_response(data)

    def search_by_year(self, year: int, media_type: str | None = None) -> list[SearchResult]:
        """Search for media by release year.

        Args:
            year: Release year to search for.
            media_type: Filter by media type.

        Returns:
            List of matching SearchResult items.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        params: dict[str, Any] = {"year": str(year)}
        if media_type:
            type_code = _TYPE_MAP.get(media_type.lower(), media_type)
            params["type"] = type_code

        data = http.get("/library/all", params=params)

        return self._parse_library_response(data)

    def search_by_genre(self, genre: str, media_type: str | None = None) -> list[SearchResult]:
        """Search for media by genre.

        Args:
            genre: Genre name to search for (e.g. 'Action', 'Comedy').
            media_type: Filter by media type.

        Returns:
            List of matching SearchResult items.
        """
        if not genre:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        params: dict[str, Any] = {"genre": genre}
        if media_type:
            type_code = _TYPE_MAP.get(media_type.lower(), media_type)
            params["type"] = type_code

        data = http.get("/library/all", params=params)

        return self._parse_library_response(data)

    def find_similar(self, key: str | int, limit: int = 20) -> list[SimilarMedia]:
        """Find media similar to a given item.

        Args:
            key: Rating key of the reference item.
            limit: Maximum number of similar items to return.

        Returns:
            List of SimilarMedia items.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        key_str = str(key)

        params = {"limit": str(limit)}
        data = http.get(f"/library/metadata/{key_str}/similar", params=params)

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        results: list[SimilarMedia] = []
        for item in raw_metadata:
            media_type = MediaType.from_plex_type(item.get("type", ""))
            results.append(
                SimilarMedia(
                    key=str(item.get("ratingKey", item.get("key", ""))),
                    title=item.get("title", ""),
                    media_type=media_type,
                    year=_safe_int(item.get("year")),
                    similarity=_safe_int(item.get("similarity")),
                    thumb=item.get("thumb") or None,
                )
            )

        return results

    def search_tmdb(
        self, query: str, media_type: str = "movie", year: int | None = None
    ) -> list[SearchResult]:
        """Search for media using the Plex Hub search with TMDB integration.

        This is a convenience wrapper around search_advanced that focuses
        on finding matches suitable for TMDB cross-referencing.

        Args:
            query: Search query string.
            media_type: Media type to search for ('movie' or 'show').
            year: Optional release year to narrow results.

        Returns:
            List of matching SearchResult items.
        """
        if not query:
            return []

        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        params: dict[str, Any] = {"query": query}
        type_code = _TYPE_MAP.get(media_type.lower(), "1")
        params["type"] = type_code

        if year:
            params["year"] = str(year)

        data = http.get("/hubs/search", params=params)

        if data is None:
            return []

        results: list[SearchResult] = []
        container = data.get("MediaContainer", data)
        hubs = container.get("Hub", [])

        if isinstance(hubs, dict):
            hubs = [hubs]

        for hub in hubs:
            metadata = hub.get("Metadata", [])
            if isinstance(metadata, dict):
                metadata = [metadata]
            results.extend(_parse_search_result(item) for item in metadata)

        return results

    # --- Private helpers -------------------------------------------------------

    @staticmethod
    def _parse_library_response(data: Any) -> list[SearchResult]:
        """Parse a /library/all API response into SearchResult list.

        Args:
            data: Raw API response dict, or None.

        Returns:
            List of SearchResult items (empty if data is None).
        """
        if data is None:
            return []

        container = data.get("MediaContainer", data)
        raw_metadata = container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            raw_metadata = [raw_metadata]

        return [_parse_search_result(item) for item in raw_metadata]
