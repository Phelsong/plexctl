"""Shoko Server service for querying anime metadata and file information.

Provides methods to query Shoko's API for series, episodes, files,
and cross-reference data to help triage file parsing issues in Plex.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from plexctl.models import (
    BatchFixResult,
    CrcAuditReport,
    CrcAuditResult,
    FixResult,
    PlexMatch,
    PlexMatchBatchResult,
    PlexMatchEntry,
    PlexMatchResult,
    ShokoEpisode,
    ShokoEpisodeType,
    ShokoFile,
    ShokoFileLocation,
    ShokoGroup,
    ShokoMismatch,
    ShokoSeasonEntry,
    ShokoSeries,
    ShokoSeriesIDs,
    ShokoSeriesSizes,
    TmdbLinkResult,
    TmdbOrdering,
    TmdbSearchResult,
    TriageAction,
    TriageIssue,
    TriageIssueType,
    TriageReport,
    TriageSeverity,
)

if TYPE_CHECKING:
    from plexctl.plugins.shoko.client import ShokoClient

logger = logging.getLogger(__name__)

_DEFAULT_PAGE_SIZE = 100


class ShokoService:
    """Service for querying Shoko Server to triage file issues.

    Provides methods to:
    - List and search series
    - Get episode details with AniDB/TMDB cross-references
    - Find files and their associations
    - Detect mismatches between Shoko and Plex data

    Args:
        client: Connected ShokoClient instance.
    """

    def __init__(self, client: ShokoClient) -> None:
        self._client = client

    # --- Series operations ---------------------------------------------------

    def list_series(
        self,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[ShokoSeries], int]:
        """List all series from Shoko.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (series_list, total_count).
        """
        items, total = self._client.get_list(
            "/Series",
            {"pageSize": page_size, "page": page},
        )
        return [self._parse_series(s) for s in items], total

    def get_series(self, series_id: int) -> ShokoSeries:
        """Get full details for a single series.

        Args:
            series_id: Shoko series ID.

        Returns:
            ShokoSeries with full details including AniDB/TMDB data.
        """
        raw = self._client.get(
            f"/Series/{series_id}",
            {"includeDataFrom": "AniDB,TMDB"},
        )
        return self._parse_series(raw)

    def search_series(self, query: str) -> list[ShokoSeries]:
        """Search series by name.

        Args:
            query: Search string to match against series names.

        Returns:
            List of matching series.
        """
        items, _ = self._client.get_list(
            "/Series",
            {"search": query, "pageSize": 50},
        )
        return [self._parse_series(s) for s in items]

    # --- Episode operations -------------------------------------------------

    def list_episodes(
        self,
        series_id: int,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[ShokoEpisode], int]:
        """List episodes for a series.

        Args:
            series_id: Shoko series ID.
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (episode_list, total_count).
        """
        items, total = self._client.get_list(
            f"/Series/{series_id}/Episode",
            {"pageSize": page_size, "page": page, "includeDataFrom": "AniDB,TMDB"},
        )
        return [self._parse_episode(e) for e in items], total

    def get_episode(self, episode_id: int) -> ShokoEpisode:
        """Get full details for a single episode.

        Args:
            episode_id: Shoko episode ID.

        Returns:
            ShokoEpisode with AniDB/TMDB cross-references.
        """
        raw = self._client.get(
            f"/Episode/{episode_id}",
            {"includeDataFrom": "AniDB,TMDB"},
        )
        return self._parse_episode(raw)

    # --- File operations ----------------------------------------------------

    def list_files(
        self,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[ShokoFile], int]:
        """List all files tracked by Shoko.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (file_list, total_count).
        """
        items, total = self._client.get_list(
            "/File",
            {"pageSize": page_size, "page": page, "include": "MediaInfo,XRefs"},
        )
        return [self._parse_file(f) for f in items], total

    def list_series_files(
        self,
        series_id: int,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[ShokoFile], int]:
        """List files for a specific series.

        Args:
            series_id: Shoko series ID.
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (file_list, total_count).
        """
        items, total = self._client.get_list(
            f"/Series/{series_id}/File",
            {"pageSize": page_size, "page": page, "include": "XRefs"},
        )
        return [self._parse_file(f) for f in items], total

    def get_file(self, file_id: int) -> ShokoFile:
        """Get full details for a single file.

        Args:
            file_id: Shoko file ID.

        Returns:
            ShokoFile with cross-references.
        """
        raw = self._client.get(
            f"/File/{file_id}",
            {"include": "MediaInfo,XRefs"},
        )
        return self._parse_file(raw)

    def search_file_by_path(self, path_suffix: str) -> list[ShokoFile]:
        """Search for files by path suffix (path-param endpoint).

        Uses Shoko's PathEndsWith path-param endpoint to find files whose
        path ends with the given string.

        NOTE: This endpoint double-encodes % characters in URLs, causing
        HTTP 400 for filenames containing %CRC. Use search_file_by_path_query
        for those cases.

        Args:
            path_suffix: Path suffix to search for.

        Returns:
            List of matching ShokoFile objects.
        """
        raw_items = self._client.get(
            f"/File/PathEndsWith/{path_suffix}",
            {"include": "XRefs"},
        )
        # This endpoint returns a list directly, not a paginated response
        if not isinstance(raw_items, list):
            return []
        return [self._parse_file(item) for item in raw_items if isinstance(item, dict)]

    def search_file_by_path_query(self, path_suffix: str) -> list[ShokoFile]:
        """Search for files by path suffix (query-param endpoint).

        Uses Shoko's PathEndsWith query-param endpoint which correctly handles
        special characters like %CRC in filenames. This is the preferred method
        when filenames may contain percent-encoded placeholders.

        Args:
            path_suffix: Path suffix to search for.

        Returns:
            List of matching ShokoFile objects.
        """
        raw_items = self._client.get(
            "/File/PathEndsWith",
            {"path": path_suffix, "include": "XRefs"},
        )
        if not isinstance(raw_items, list):
            return []
        return [self._parse_file(item) for item in raw_items if isinstance(item, dict)]

    # --- Group operations ---------------------------------------------------

    def list_groups(
        self,
        page: int = 1,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> tuple[list[ShokoGroup], int]:
        """List all groups from Shoko.

        Groups organize related series (e.g. all seasons of a franchise).

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.

        Returns:
            Tuple of (group_list, total_count).
        """
        items, total = self._client.get_list(
            "/Group",
            {"pageSize": page_size, "page": page},
        )
        return [self._parse_group(g) for g in items], total

    # --- Triage operations --------------------------------------------------

    def find_unlinked_files(self) -> list[ShokoFile]:
        """Find files that are not linked to any series or episode.

        These represent files Shoko has ingested but couldn't match
        to any known anime series.

        Returns:
            List of ShokoFile objects with no series association.
        """
        unlinked: list[ShokoFile] = []
        page = 1
        total = None

        while total is None or len(unlinked) < total:
            files, total = self.list_files(page=page, page_size=_DEFAULT_PAGE_SIZE)
            unlinked.extend(
                f for f in files if f.series_id is None and not f.is_ignored
            )
            page += 1
            # Safety limit to prevent infinite loops
            if page > (total // _DEFAULT_PAGE_SIZE) + 2:
                break

        return unlinked

    def find_problem_series(self) -> list[ShokoMismatch]:
        """Find series with potential issues.

        Looks for:
        - Series with zero local episodes (no files matched)
        - Series with no TMDB links (won't get season/ep mapping)
        - Series with multiple TMDB links (ambiguous mapping)

        Returns:
            List of ShokoMismatch objects describing each problem.
        """
        mismatches: list[ShokoMismatch] = []
        page = 1
        total = None

        while total is None or len(mismatches) < total * 2:
            series_list, total = self.list_series(page=page)
            for s in series_list:
                # Series with 0 local episodes (file matching failed)
                if s.local_sizes.episodes + s.local_sizes.specials == 0:
                    mismatches.append(
                        ShokoMismatch(
                            mismatch_type="no_local_episodes",
                            shoko_id=s.ids.id,
                            name=s.name,
                            detail=f"Series '{s.name}' has no local episodes matched",
                            severity="error",
                        )
                    )

                # Series with no TMDB link (can't get season/ep mapping)
                if not s.ids.tmdb_show and not s.ids.tmdb_movie:
                    mismatches.append(
                        ShokoMismatch(
                            mismatch_type="no_tmdb_link",
                            shoko_id=s.ids.id,
                            name=s.name,
                            detail=(
                                f"Series '{s.name}' has no TMDB link for season mapping"
                            ),
                            severity="warning",
                        )
                    )

                # Series with multiple TMDB links (ambiguous mapping)
                if len(s.ids.tmdb_show) > 1:
                    mismatches.append(
                        ShokoMismatch(
                            mismatch_type="multiple_tmdb_links",
                            shoko_id=s.ids.id,
                            name=s.name,
                            detail=(
                                f"Series '{s.name}' has {len(s.ids.tmdb_show)} "
                                f"TMDB show links"
                            ),
                            severity="info",
                        )
                    )

            page += 1
            if page > (total // _DEFAULT_PAGE_SIZE) + 2:
                break

        return mismatches

    # --- TMDB link operations -----------------------------------------------

    def search_tmdb_shows(
        self,
        query: str,
        year: int | None = None,
    ) -> list[TmdbSearchResult]:
        """Search TMDB for TV shows via Shoko's online search.

        Args:
            query: Search string to match against show titles.
            year: Optional first aired year filter.

        Returns:
            List of matching TMDB search results.
        """
        params: dict[str, Any] = {"query": query}
        if year:
            params["year"] = year

        raw_items, _ = self._client.get_list(
            "/Tmdb/Show/Online/Search",
            params,
        )
        return [self._parse_tmdb_search(item) for item in raw_items]

    def search_tmdb_movies(
        self,
        query: str,
        year: int | None = None,
    ) -> list[TmdbSearchResult]:
        """Search TMDB for movies via Shoko's online search.

        Args:
            query: Search string to match against movie titles.
            year: Optional release year filter.

        Returns:
            List of matching TMDB search results.
        """
        params: dict[str, Any] = {"query": query}
        if year:
            params["year"] = year

        raw_items, _ = self._client.get_list(
            "/Tmdb/Movie/Online/Search",
            params,
        )
        return [self._parse_tmdb_search(item) for item in raw_items]

    def link_tmdb_show(
        self,
        series_id: int,
        tmdb_show_id: int,
        *,
        replace: bool = False,
        refresh: bool = False,
    ) -> TmdbLinkResult:
        """Link a TMDB show to a Shoko series.

        Args:
            series_id: Shoko series ID to link.
            tmdb_show_id: TMDB show ID to link.
            replace: If True, replace all existing TMDB links.
            refresh: If True, force refresh metadata after linking.

        Returns:
            TmdbLinkResult indicating success or failure.
        """
        try:
            self._client.post(
                f"/Series/{series_id}/TMDB/Show",
                json={"ID": tmdb_show_id, "Replace": replace, "Refresh": refresh},
            )
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_show_id,
                action="linked",
                success=True,
            )
        except Exception as exc:
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_show_id,
                action="linked",
                success=False,
                error=str(exc),
            )

    def link_tmdb_movie(
        self,
        series_id: int,
        tmdb_movie_id: int,
        anidb_episode_id: int,
        *,
        replace: bool = False,
        refresh: bool = False,
    ) -> TmdbLinkResult:
        """Link a TMDB movie to a Shoko series episode.

        TMDB movie links require specifying which AniDB episode the movie maps to.
        Use the AniDB episode ID (not Shoko internal episode ID).

        Args:
            series_id: Shoko series ID to link.
            tmdb_movie_id: TMDB movie ID to link.
            anidb_episode_id: AniDB episode ID to link the movie to.
            replace: If True, replace all existing TMDB links.
            refresh: If True, force refresh metadata after linking.

        Returns:
            TmdbLinkResult indicating success or failure.
        """
        try:
            self._client.post(
                f"/Series/{series_id}/TMDB/Movie",
                json={
                    "ID": tmdb_movie_id,
                    "EpisodeID": anidb_episode_id,
                    "Replace": replace,
                    "Refresh": refresh,
                },
            )
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_movie_id,
                action="linked",
                success=True,
            )
        except Exception as exc:
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_movie_id,
                action="linked",
                success=False,
                error=str(exc),
            )

    def unlink_tmdb_show(
        self,
        series_id: int,
        tmdb_show_id: int,
        *,
        purge: bool = False,
    ) -> TmdbLinkResult:
        """Remove a TMDB show link from a Shoko series.

        Args:
            series_id: Shoko series ID to unlink.
            tmdb_show_id: TMDB show ID to remove.
            purge: If True, purge cached metadata for the link.

        Returns:
            TmdbLinkResult indicating success or failure.
        """
        try:
            self._client.delete(
                f"/Series/{series_id}/TMDB/Show",
                json={"ID": tmdb_show_id, "Purge": purge},
            )
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_show_id,
                action="unlinked",
                success=True,
            )
        except Exception as exc:
            return TmdbLinkResult(
                series_id=series_id,
                tmdb_id=tmdb_show_id,
                action="unlinked",
                success=False,
                error=str(exc),
            )

    def refresh_tmdb_show(self, series_id: int) -> TmdbLinkResult:
        """Refresh all TMDB show metadata for a Shoko series.

        Args:
            series_id: Shoko series ID whose TMDB links to refresh.

        Returns:
            TmdbLinkResult indicating success or failure.
        """
        try:
            self._client.post(
                f"/Series/{series_id}/TMDB/Show/Action/Refresh",
                json={"Immediate": True, "Force": True, "DownloadImages": True},
            )
            return TmdbLinkResult(
                series_id=series_id,
                action="refreshed",
                success=True,
            )
        except Exception as exc:
            return TmdbLinkResult(
                series_id=series_id,
                action="refreshed",
                success=False,
                error=str(exc),
            )

    # --- Parse helpers -------------------------------------------------------

    def _parse_series(self, raw: dict[str, Any]) -> ShokoSeries:
        """Parse a Shoko API series response into a ShokoSeries model."""
        ids_raw = raw.get("IDs", {})
        sizes_raw = raw.get("Sizes", {})
        local_raw = sizes_raw.get("Local", {})
        total_raw = sizes_raw.get("Total", {})

        ids = ShokoSeriesIDs(
            id=ids_raw.get("ID", 0),
            anidb=ids_raw.get("AniDB"),
            tmdb_show=ids_raw.get("TMDB", {}).get("Show", [])
            if isinstance(ids_raw.get("TMDB"), dict)
            else [],
            tmdb_movie=ids_raw.get("TMDB", {}).get("Movie", [])
            if isinstance(ids_raw.get("TMDB"), dict)
            else [],
            tvdb=ids_raw.get("TvDB", [])
            if isinstance(ids_raw.get("TvDB"), list)
            else [],
            imdb=ids_raw.get("IMDB", [])
            if isinstance(ids_raw.get("IMDB"), list)
            else [],
        )

        local_sizes = ShokoSeriesSizes(
            episodes=local_raw.get("Episodes", 0),
            specials=local_raw.get("Specials", 0),
            credits=local_raw.get("Credits", 0),
            trailers=local_raw.get("Trailers", 0),
            parodies=local_raw.get("Parodies", 0),
            others=local_raw.get("Others", 0),
            unknown=local_raw.get("Unknown", 0),
        )

        total_sizes = ShokoSeriesSizes(
            episodes=total_raw.get("Episodes", 0),
            specials=total_raw.get("Specials", 0),
            credits=total_raw.get("Credits", 0),
            trailers=total_raw.get("Trailers", 0),
            parodies=total_raw.get("Parodies", 0),
            others=total_raw.get("Others", 0),
            unknown=total_raw.get("Unknown", 0),
        )

        return ShokoSeries(
            ids=ids,
            name=raw.get("Name", "Unknown"),
            description=raw.get("Description"),
            episode_count=sizes_raw.get("Total", {}).get("Episodes", 0)
            + sizes_raw.get("Total", {}).get("Specials", 0),
            local_sizes=local_sizes,
            total_sizes=total_sizes,
        )

    def _parse_episode(self, raw: dict[str, Any]) -> ShokoEpisode:
        """Parse a Shoko API episode response into a ShokoEpisode model."""
        anidb_raw = raw.get("AniDB", {})
        tmdb_raw = raw.get("TMDB", {})

        # Get season, episode numbers, and TMDB episode ID from cross-reference
        season_number = None
        tmdb_episode_number = None
        tmdb_episode_id = None
        tmdb_episodes = (
            tmdb_raw.get("Episodes", []) if isinstance(tmdb_raw, dict) else []
        )
        if tmdb_episodes:
            season_number = tmdb_episodes[0].get("SeasonNumber")
            tmdb_episode_number = tmdb_episodes[0].get("EpisodeNumber")
            tmdb_episode_id = tmdb_episodes[0].get("ID")

        # Shoko API returns type as string ("Episode", "Special") when
        # includeDataFrom=AniDB is used, or as numeric ID otherwise.
        anidb_type = anidb_raw.get("Type", 0) if isinstance(anidb_raw, dict) else 0

        # Episode ID is nested under IDs.ID in v3 API
        ids_raw = raw.get("IDs", {})
        episode_id = ids_raw.get("ID", raw.get("ID", 0))

        return ShokoEpisode(
            id=episode_id,
            name=raw.get(
                "Name", anidb_raw.get("Title") if isinstance(anidb_raw, dict) else None
            ),
            episode_number=anidb_raw.get("EpisodeNumber")
            if isinstance(anidb_raw, dict)
            else None,
            episode_type=ShokoEpisodeType.from_api_type(anidb_type),
            season_number=season_number,
            tmdb_episode_number=tmdb_episode_number,
            tmdb_episode_id=tmdb_episode_id,
            anidb_id=anidb_raw.get("ID") if isinstance(anidb_raw, dict) else None,
            is_hidden=raw.get("IsHidden", False),
        )

    def _parse_file(self, raw: dict[str, Any]) -> ShokoFile:
        """Parse a Shoko API file response into a ShokoFile model."""
        # Extract series cross-references
        series_ids_list = raw.get("SeriesIDs", [])
        series_id = None
        series_name = None
        episode_ids: list[int] = []

        if series_ids_list:
            first_series = (
                series_ids_list[0]
                if isinstance(series_ids_list, list)
                else series_ids_list
            )
            if isinstance(first_series, dict):
                series_id = first_series.get("SeriesID", {}).get("ID")
                series_name = first_series.get("SeriesID", {}).get("Name")
                episode_ids = [
                    ep.get("ID", 0)
                    for ep in first_series.get("EpisodeIDs", [])
                    if isinstance(ep, dict)
                ]

        # Extract file location
        locations = raw.get("Locations", [])
        location = ShokoFileLocation(
            relative_path=locations[0].get("RelativePath", "") if locations else "",
            is_accessible=locations[0].get("IsAccessible", True) if locations else True,
            managed_folder_id=locations[0].get("ManagedFolderID")
            if locations
            else None,
        )

        # Extract filename from path
        filename = None
        if location.relative_path:
            filename = (
                location.relative_path.rsplit("/", 1)[-1]
                if "/" in location.relative_path
                else location.relative_path
            )

        # Extract hashes (list of {Type, Value} objects)
        hashes_raw = raw.get("Hashes", [])
        crc32 = None
        ed2k = None
        sha1 = None
        if isinstance(hashes_raw, list):
            for h in hashes_raw:
                if isinstance(h, dict):
                    hash_type = h.get("Type", "")
                    hash_value = h.get("Value")
                    if hash_type == "CRC32":
                        crc32 = hash_value
                    elif hash_type == "ED2K":
                        ed2k = hash_value
                    elif hash_type == "SHA1":
                        sha1 = hash_value

        # Extract duration (Shoko returns timespan string, e.g., "00:23:40.0450000")
        duration_raw = raw.get("Duration")
        duration_ms = None
        if duration_raw and isinstance(duration_raw, str):
            # Parse "HH:MM:SS.fffffff" format
            with contextlib.suppress(ValueError):
                parts = duration_raw.split(":")
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = float(parts[2])
                    duration_ms = int((hours * 3600 + minutes * 60 + seconds) * 1000)

        return ShokoFile(
            id=raw.get("ID", 0),
            filename=filename,
            relative_path=location.relative_path or None,
            is_accessible=location.is_accessible,
            series_id=series_id,
            series_name=series_name,
            episode_ids=episode_ids,
            is_variation=raw.get("IsVariation", False),
            is_ignored=raw.get("IsIgnored", False),
            resolution=raw.get("Resolution"),
            duration=duration_ms,
            crc32=crc32,
            ed2k=ed2k,
            sha1=sha1,
        )

    def _parse_group(self, raw: dict[str, Any]) -> ShokoGroup:
        """Parse a Shoko API group response into a ShokoGroup model."""
        return ShokoGroup(
            id=raw.get("IDs", {}).get("ID", 0),
            name=raw.get("Name", "Unknown"),
            series_count=raw.get("Sizes", {}).get("Series", 0),
            series_ids=raw.get("IDs", {}).get("SeriesIDs", [])
            if isinstance(raw.get("IDs", {}).get("SeriesIDs"), list)
            else [],
        )

    def _parse_tmdb_search(self, raw: dict[str, Any]) -> TmdbSearchResult:
        """Parse a TMDB online search result into a TmdbSearchResult model."""
        # Extract year from FirstAiredAt (shows) or ReleasedAt (movies)
        first_aired = raw.get("FirstAiredAt") or raw.get("ReleasedAt")
        year = None
        if first_aired and isinstance(first_aired, str) and len(first_aired) >= 4:
            with contextlib.suppress(ValueError):
                year = int(first_aired[:4])

        return TmdbSearchResult(
            id=raw.get("ID", 0),
            name=raw.get("Title", "Unknown"),
            overview=raw.get("Overview"),
            year=year,
            first_aired=first_aired,
            poster_url=raw.get("Poster"),
        )

    # --- CRC audit operations ------------------------------------------------

    def audit_crc_hashes(self) -> tuple[list[CrcAuditResult], CrcAuditReport]:
        """Audit all files for CRC hash completeness.

        Checks each file's relative_path for %CRC placeholders versus real
        CRC32 hashes, and groups results by series.

        Returns:
            Tuple of (per-series results, aggregate report).
        """
        import re

        crc_pattern = re.compile(r"\[([0-9A-Fa-f]{8})\]")
        placeholder_pattern = re.compile(r"\[%CRC\]")

        series_data: dict[int, CrcAuditResult] = {}
        total_files = 0
        files_with_crc = 0
        files_missing_crc = 0
        files_no_bracket = 0

        page = 1
        total = None
        while total is None or total_files < total:
            files, total = self.list_files(page=page, page_size=_DEFAULT_PAGE_SIZE)
            page += 1

            for f in files:
                total_files += 1
                path = f.relative_path or f.filename or ""

                has_real_crc = bool(crc_pattern.search(path))
                has_placeholder = bool(placeholder_pattern.search(path))

                if has_real_crc:
                    files_with_crc += 1
                elif has_placeholder:
                    files_missing_crc += 1
                else:
                    files_no_bracket += 1

                # Group by series
                if f.series_id is not None:
                    if f.series_id not in series_data:
                        series_data[f.series_id] = CrcAuditResult(
                            series_id=f.series_id,
                            series_name=f.series_name or "Unknown",
                        )
                    result = series_data[f.series_id]
                    result.total_files += 1
                    if has_real_crc:
                        result.files_with_crc += 1
                    elif has_placeholder:
                        result.files_missing_crc += 1
                        if len(result.missing_crc_paths) < 5:
                            result.missing_crc_paths.append(path)
                    else:
                        result.files_no_bracket += 1

            if page > (total // _DEFAULT_PAGE_SIZE) + 2:
                break

        # Build report
        series_missing = sorted(
            [r for r in series_data.values() if r.files_missing_crc > 0],
            key=lambda r: r.files_missing_crc,
            reverse=True,
        )

        report = CrcAuditReport(
            total_series=len(series_data),
            total_files=total_files,
            files_with_crc=files_with_crc,
            files_missing_crc=files_missing_crc,
            files_no_bracket=files_no_bracket,
            series_missing_crc=series_missing,
        )

        return list(series_data.values()), report

    def rehash_file(self, file_id: int) -> bool:
        """Trigger a rehash for a single file.

        Args:
            file_id: Shoko internal file ID.

        Returns:
            True if rehash was triggered successfully.
        """
        try:
            self._client.post(f"/File/{file_id}/Rehash")
            return True
        except Exception:
            return False

    def rescan_file(self, file_id: int) -> bool:
        """Trigger a rescan for a single file on AniDB.

        Args:
            file_id: Shoko internal file ID.

        Returns:
            True if rescan was triggered successfully.
        """
        try:
            self._client.post(f"/File/{file_id}/Rescan")
            return True
        except Exception:
            return False

    def batch_rehash_missing_crc(self) -> BatchFixResult:
        """Trigger rehash for all files missing CRC32 hashes.

        Runs a CRC audit to identify files with %CRC placeholders,
        then triggers rehash for each file that lacks a CRC32 hash
        in both filename and the Hashes field.

        Returns:
            BatchFixResult with total/succeeded/failed counts.
        """
        import re

        crc_pattern = re.compile(r"\[([0-9A-Fa-f]{8})\]")

        succeeded = 0
        failed = 0
        results: list[FixResult] = []
        total = 0

        page = 1
        file_total = None
        while file_total is None or total < file_total:
            files, file_total = self.list_files(page=page, page_size=_DEFAULT_PAGE_SIZE)
            page += 1

            if not files:
                break

            for f in files:
                path = f.relative_path or f.filename or ""
                has_real_crc_in_name = bool(crc_pattern.search(path))
                has_crc32_hash = bool(f.crc32)

                if has_real_crc_in_name and has_crc32_hash:
                    continue  # Already has CRC in both name and hash

                total += 1
                success = self.rehash_file(f.id)
                if success:
                    succeeded += 1
                    results.append(
                        FixResult(
                            key=str(f.id),
                            title=path[-60:] if path else "unknown",
                            action="rehash",
                            success=True,
                        )
                    )
                else:
                    failed += 1
                    results.append(
                        FixResult(
                            key=str(f.id),
                            title=path[-60:] if path else "unknown",
                            action="rehash",
                            success=False,
                            error="rehash failed",
                        )
                    )

            if page > (file_total // _DEFAULT_PAGE_SIZE) + 2:
                break

        return BatchFixResult(
            total=total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    def trigger_import(self) -> bool:
        """Trigger Shoko to import new files.

        Returns:
            True if import was triggered successfully.
        """
        try:
            self._client.get("/Action/ImportNewFiles")
            return True
        except Exception:
            return False

    def trigger_update_media_info(self) -> bool:
        """Trigger Shoko to update all media info.

        Returns:
            True if update was triggered successfully.
        """
        try:
            self._client.get("/Action/UpdateAllMediaInfo")
            return True
        except Exception:
            return False

    # --- PlexMatch generation ------------------------------------------------

    def generate_plexmatch(
        self,
        series_id: int,
        plexmatch_dir: str | None = None,
        ordering_id: str | None = None,
        *,
        append: bool = False,
        append_dir: str | None = None,
    ) -> PlexMatch:
        """Generate a .plexmatch file for a series using Shoko data.

        Gathers series metadata (title, year, external IDs) and file-to-episode
        mappings from Shoko to produce a PlexMatch object that can be written
        as a .plexmatch file in the series directory.

        Args:
            series_id: Shoko series ID to generate plexmatch for.
            plexmatch_dir: Directory name where the .plexmatch will be written
                (e.g. "WITCH WATCH"). When provided, episode filenames use
                paths relative to this directory so that files in season
                subdirectories are correctly referenced.
            ordering_id: TMDB episode ordering ID (e.g. "62f98314175051007c594bdf"
                for One Piece TVDB Order). When provided, fetches the ordering's
                season/episode structure and uses it instead of Shoko's stored
                TMDB mapping. Use list_tmdb_orderings() to discover available
                orderings for a show.
            append: If True and the target .plexmatch file exists, merge
                existing entries with new ones (new entries override duplicates
                by season/episode key).
            append_dir: Full path to the directory containing the .plexmatch
                file for append mode. When not provided, falls back to
                plexmatch_dir (which may be just a directory name).

        Returns:
            PlexMatch with all metadata and episode mappings.
        """
        series = self.get_series(series_id)

        # Extract year from AniDB air date if available
        year = self._extract_series_year(series_id)

        # Collect external IDs
        tvdb_id = series.ids.tvdb[0] if series.ids.tvdb else None
        imdb_id = series.ids.imdb[0] if series.ids.imdb else None
        tmdb_id = series.ids.tmdb_show[0] if series.ids.tmdb_show else None

        # Fetch ordering episode map if an alternate ordering is requested
        ordering_episode_map: dict[int, tuple[int, int]] | None = None
        if ordering_id and tmdb_id:
            ordering_episode_map = self.fetch_ordering_episode_map(tmdb_id, ordering_id)

        # Gather episodes and files, then match them
        entries = self._build_plexmatch_entries(
            series_id,
            plexmatch_dir=plexmatch_dir,
            ordering_episode_map=ordering_episode_map,
        )

        plexmatch = PlexMatch(
            title=series.name,
            year=year,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            entries=entries,
        )

        if append:
            read_dir = append_dir or plexmatch_dir
            if read_dir:
                existing = self._read_existing_plexmatch(read_dir)
                if existing is not None:
                    plexmatch = plexmatch.merge(existing)

        return plexmatch

    def generate_plexmatch_combined(
        self,
        series_ids: list[int],
        title: str | None = None,
        plexmatch_dir: str | None = None,
        ordering_id: str | None = None,
        *,
        append: bool = False,
        append_dir: str | None = None,
    ) -> PlexMatch:
        """Generate a combined .plexmatch for multiple series sharing a TMDB show.

        When anime series are split across multiple Shoko entries (e.g. Spy x
        Family has separate entries per cour), they all map to one TMDB
        show with proper season/episode numbering. This method merges all
        episodes from the given series into a single PlexMatch file.

        Uses the first series for metadata (title, year, IDs) unless overridden.

        Args:
            series_ids: List of Shoko series IDs to combine.
            title: Override title for the plexmatch. Defaults to first series name.
            plexmatch_dir: Directory name where the .plexmatch will be written.
                When provided, episode filenames use paths relative to this
                directory.
            ordering_id: TMDB episode ordering ID. When provided, uses this
                ordering's season/episode structure instead of Shoko's stored
                TMDB mapping.
            append: If True and the target .plexmatch file exists, merge
                existing entries with new ones (new entries override duplicates
                by season/episode key).
            append_dir: Full path to the directory containing the .plexmatch
                file for append mode. When not provided, falls back to
                plexmatch_dir (which may be just a directory name).

        Returns:
            PlexMatch with merged entries from all series.
        """
        if not series_ids:
            msg = "At least one series ID is required"
            raise ValueError(msg)

        # Use first series for metadata
        first_series = self.get_series(series_ids[0])

        # Collect external IDs (prefer any series that has them)
        tvdb_id = first_series.ids.tvdb[0] if first_series.ids.tvdb else None
        imdb_id = first_series.ids.imdb[0] if first_series.ids.imdb else None
        tmdb_id = first_series.ids.tmdb_show[0] if first_series.ids.tmdb_show else None
        year = self._extract_series_year(series_ids[0])

        # If metadata IDs are missing from first series, check others
        if not tvdb_id or not imdb_id or not tmdb_id:
            for sid in series_ids[1:]:
                s = self.get_series(sid)
                if not tvdb_id and s.ids.tvdb:
                    tvdb_id = s.ids.tvdb[0]
                if not imdb_id and s.ids.imdb:
                    imdb_id = s.ids.imdb[0]
                if not tmdb_id and s.ids.tmdb_show:
                    tmdb_id = s.ids.tmdb_show[0]
                if tvdb_id and imdb_id and tmdb_id:
                    break

        # Fetch ordering episode map if an alternate ordering is requested
        ordering_episode_map: dict[int, tuple[int, int]] | None = None
        if ordering_id and tmdb_id:
            ordering_episode_map = self.fetch_ordering_episode_map(tmdb_id, ordering_id)

        # Merge entries from all series, using TMDB absolute numbering
        all_entries: list[PlexMatchEntry] = []
        seen_keys: set[tuple[int, int]] = set()
        for series_id in series_ids:
            entries = self._build_plexmatch_entries(
                series_id,
                plexmatch_dir=plexmatch_dir,
                ordering_episode_map=ordering_episode_map,
            )
            for entry in entries:
                key = (entry.season_number, entry.episode_number)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_entries.append(entry)

        # Sort all entries by season/episode
        all_entries.sort(key=lambda e: (e.season_number, e.episode_number))

        plexmatch = PlexMatch(
            title=title or first_series.name,
            year=year,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            entries=all_entries,
        )

        if append:
            read_dir = append_dir or plexmatch_dir
            if read_dir:
                existing = self._read_existing_plexmatch(read_dir)
                if existing is not None:
                    plexmatch = plexmatch.merge(existing)

        return plexmatch

    def _extract_series_year(self, series_id: int) -> int | None:
        """Extract the year from series AniDB data.

        Falls back to TMDB first-aired date if AniDB data is unavailable.

        Args:
            series_id: Shoko series ID.

        Returns:
            The year as an integer, or None if no data available.
        """
        # Try AniDB endpoint for air date
        try:
            raw = self._client.get(f"/Series/{series_id}/AniDB")
            air_date = raw.get("AirDate") if isinstance(raw, dict) else None
            if air_date and isinstance(air_date, str) and len(air_date) >= 4:
                return int(air_date[:4])
        except Exception:
            logger.debug("AniDB year lookup failed for series %d", series_id)

        # Fallback: no year available
        return None

    # --- TMDB episode ordering -----------------------------------------------

    def list_tmdb_orderings(self, tmdb_show_id: int) -> list[TmdbOrdering]:
        """List all alternate episode orderings for a TMDB show.

        TMDB shows (especially long-running anime) can have multiple
        episode group orderings that define different season structures.
        For example, One Piece has "Sagas" (12 seasons), "TVDB Order"
        (23 seasons), "Seasons (Production)" (25 seasons), etc.

        Args:
            tmdb_show_id: TMDB TV show ID (e.g. 37854 for One Piece).

        Returns:
            List of TmdbOrdering objects describing each available ordering.

        Raises:
            httpx.HTTPStatusError: If the Shoko API returns an error.
        """
        # Plain JSON array, not a paginated {List, Total} response.
        raw_list = self._client.get(f"/TMDB/Show/{tmdb_show_id}/Ordering")
        if not isinstance(raw_list, list):
            return []
        orderings: list[TmdbOrdering] = []
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            orderings.append(
                TmdbOrdering(
                    ordering_id=str(raw.get("OrderingID", "")),
                    name=raw.get("OrderingName", ""),
                    ordering_type=raw.get("OrderingType", 0) or 0,
                    season_count=raw.get("SeasonCount", 0) or 0,
                    episode_count=raw.get("EpisodeCount", 0) or 0,
                    is_default=bool(raw.get("IsDefault", False)),
                    is_preferred=bool(raw.get("IsPreferred", False)),
                    in_use=bool(raw.get("InUse", False)),
                )
            )
        return orderings

    def fetch_ordering_episode_map(
        self, tmdb_show_id: int, ordering_id: str
    ) -> dict[int, tuple[int, int]]:
        """Fetch a mapping of TMDB episode IDs to season/episode numbers.

        Queries the Shoko API for the given ordering's season structure,
        then fetches episodes for each season to build a complete mapping
        from TMDB episode ID → (season_number, episode_number).

        The TMDB episode ID is consistent across all orderings — the same
        episode has the same ID whether it's in "Sagas" or "TVDB Order".
        Only the season/episode assignment differs.

        Args:
            tmdb_show_id: TMDB TV show ID.
            ordering_id: The OrderingID from list_tmdb_orderings()
                (e.g. "62f98314175051007c594bdf" for One Piece TVDB Order).

        Returns:
            Dict mapping TMDB episode ID → (season_number, episode_number)
            for the specified ordering. Episodes missing from this ordering
            (e.g. episodes not yet assigned) are simply absent from the dict.
        """
        # Fetch seasons for this ordering
        seasons_raw, _ = self._client.get_list(
            f"/TMDB/Show/{tmdb_show_id}/Season",
            {"alternateOrderingID": ordering_id},
        )

        episode_map: dict[int, tuple[int, int]] = {}

        for season_raw in seasons_raw:
            if not isinstance(season_raw, dict):
                continue

            season_id = str(season_raw.get("ID", ""))
            season_number = season_raw.get("SeasonNumber")

            # Skip seasons with no number (arc-based orderings without numeric seasons)
            if season_number is None:
                continue

            # Fetch episodes for this season
            episodes_raw, _ = self._client.get_list(
                f"/TMDB/Season/{season_id}/Episode",
            )

            for ep_raw in episodes_raw:
                if not isinstance(ep_raw, dict):
                    continue

                tmdb_ep_id = ep_raw.get("ID")
                ep_number = ep_raw.get("EpisodeNumber")

                if tmdb_ep_id is not None and ep_number is not None:
                    episode_map[tmdb_ep_id] = (season_number, ep_number)

        return episode_map

    def _build_plexmatch_entries(
        self,
        series_id: int,
        plexmatch_dir: str | None = None,
        ordering_episode_map: dict[int, tuple[int, int]] | None = None,
    ) -> list[PlexMatchEntry]:
        """Build episode-to-file mappings for a plexmatch file.

        Matches each episode to its file using Shoko's cross-reference data.
        Files linked to multiple episodes (multi-episode files) appear once
        per episode. Only regular episodes and specials are included;
        credits, trailers, and other types are skipped.

        Args:
            series_id: Shoko series ID.
            plexmatch_dir: Directory name where the .plexmatch file will be
                written (e.g. "WITCH WATCH"). When provided, file paths are
                computed relative to this directory so that files in season
                subdirectories use paths like "Season 01/Episode.mkv" instead
                of bare filenames. Falls back to bare filenames when the
                file's relative_path doesn't start with this prefix.
            ordering_episode_map: Optional mapping from TMDB episode ID to
                (season_number, episode_number) for an alternate ordering.
                When provided, episodes with a matching TMDB episode ID use
                this mapping instead of Shoko's stored season/episode data.

        Returns:
            List of PlexMatchEntry objects, sorted by season/episode number.
        """
        episodes, total_episodes = self.list_episodes(
            series_id,
            page_size=_DEFAULT_PAGE_SIZE,
        )

        # Paginate to get all episodes
        all_episodes = list(episodes)
        page = 2
        while len(all_episodes) < total_episodes:
            more_episodes, _ = self.list_episodes(
                series_id,
                page=page,
                page_size=_DEFAULT_PAGE_SIZE,
            )
            if not more_episodes:
                break
            all_episodes.extend(more_episodes)
            page += 1
            if page > (total_episodes // _DEFAULT_PAGE_SIZE) + 2:
                break

        # Filter to regular episodes and specials only
        relevant_episodes = [
            ep
            for ep in all_episodes
            if ep.episode_type in (ShokoEpisodeType.EPISODE, ShokoEpisodeType.SPECIAL)
            and not ep.is_hidden
            and ep.episode_number is not None
        ]

        if not relevant_episodes:
            return []

        # Gather files for this series only (much faster than fetching all files)
        series_files: list[ShokoFile] = []
        page = 1
        file_total = None
        while file_total is None or len(series_files) < file_total:
            page_files, file_total = self.list_series_files(
                series_id,
                page=page,
                page_size=_DEFAULT_PAGE_SIZE,
            )
            series_files.extend(page_files)
            page += 1
            if page > (file_total // _DEFAULT_PAGE_SIZE) + 2:
                break

        # Filter out variation and ignored files
        series_files_filtered = [
            f
            for f in series_files
            if not f.is_variation and not f.is_ignored and f.filename
        ]

        # Build episode_id -> episode mapping
        episode_by_id = {ep.id: ep for ep in relevant_episodes}

        # Build episode_id -> file mapping (first file per episode wins)
        episode_to_file: dict[int, ShokoFile] = {}
        for file in series_files_filtered:
            for ep_id in file.episode_ids:
                if ep_id in episode_by_id and ep_id not in episode_to_file:
                    episode_to_file[ep_id] = file

        # Compute derived (season, episode) assignment for each episode.
        # When an ordering_episode_map is provided, look up the TMDB episode
        # ID in the map first. If found, use that ordering's season/episode
        # assignment. If not found (episode not yet in the ordering), fall
        # back to Shoko's stored TMDB data.
        # TMDB season takes priority; specials default to season 0.
        # When TMDB provides no season AND no episode mapping (both None),
        # the episode has no place in the TMDB season structure and is
        # treated as a special (S00). This handles cases like OVAs that
        # Shoko classifies as "Episode" type but TMDB treats as specials.
        def _assign_season_episode(
            ep: ShokoEpisode,
        ) -> tuple[int, int]:
            if ordering_episode_map and ep.tmdb_episode_id is not None:
                ordering_match = ordering_episode_map.get(ep.tmdb_episode_id)
                if ordering_match is not None:
                    return ordering_match
                # Not in ordering map: fall through to stored data

            if ep.season_number is not None:
                return (
                    ep.season_number,
                    ep.tmdb_episode_number or ep.episode_number or 0,
                )

            if ep.episode_type == ShokoEpisodeType.SPECIAL or (
                ep.tmdb_episode_number is None and ep.season_number is None
            ):
                return (0, ep.episode_number or 0)

            return (1, ep.tmdb_episode_number or ep.episode_number or 0)

        # Build entries sorted by derived season/episode, deduplicating by
        # (season, episode) so that multiple Shoko episodes mapping to the
        # same season/episode number produce only one entry (first file wins).
        seen_keys: set[tuple[int, int]] = set()
        entries: list[PlexMatchEntry] = []
        for ep in sorted(
            relevant_episodes,
            key=lambda e: _assign_season_episode(e),
        ):
            matched_file = episode_to_file.get(ep.id)
            if matched_file is None or matched_file.filename is None:
                continue

            # Compute the path relative to the .plexmatch file location.
            # ShokoFile.relative_path is relative to the managed folder root
            # (e.g. "WITCH WATCH/Season 01/Ep01.mkv"). When plexmatch_dir is
            # provided (e.g. "WITCH WATCH"), strip it to get the path relative
            # to the .plexmatch file ("Season 01/Ep01.mkv").
            filepath = matched_file.filename
            if plexmatch_dir and matched_file.relative_path:
                prefix = plexmatch_dir + "/"
                if matched_file.relative_path.startswith(prefix):
                    filepath = matched_file.relative_path[len(prefix) :]

            season, episode_num = _assign_season_episode(ep)
            key = (season, episode_num)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entries.append(
                PlexMatchEntry(
                    season_number=season,
                    episode_number=episode_num,
                    filename=filepath,
                )
            )

        return sorted(entries, key=lambda e: (e.season_number, e.episode_number))

    @staticmethod
    def _read_existing_plexmatch(target_dir: str) -> PlexMatch | None:
        """Read an existing .plexmatch file from the target directory.

        Args:
            target_dir: Directory where .plexmatch would be written.

        Returns:
            Parsed PlexMatch if the file exists, None otherwise.
        """
        from pathlib import Path as _Path

        plexmatch_path = _Path(target_dir) / ".plexmatch"
        if plexmatch_path.is_file():
            content = plexmatch_path.read_text(encoding="utf-8")
            return PlexMatch.parse(content)
        return None

    # --- Batch PlexMatch generation -------------------------------------------

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a series name for fuzzy matching.

        Strips common prefixes, suffixes, and punctuation to produce
        a canonical form suitable for comparing folder names with
        Shoko series names.

        Args:
            name: Raw series or folder name.

        Returns:
            Lowercased, punctuation-stripped name with common anime
            suffixes removed.
        """
        import re

        normalized = name.lower().strip()
        # Remove common anime suffixes like "(2025)", "[SubGroup]",
        # "2nd Season", "Season 3", etc.
        normalized = re.sub(r"\(?\d{4}\)?", "", normalized)  # Remove years
        normalized = re.sub(r"\[.*?\]", "", normalized)  # Remove [group] tags
        # Remove season suffixes
        for suffix in (
            "2nd season",
            "3rd season",
            "4th season",
            "final season",
            "season 2",
            "season 3",
            "season 4",
            "ova",
            "movie",
            "special",
            "tv",
            "the animation",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()
        # Remove all non-alphanumeric characters
        normalized = re.sub(r"[^a-z0-9]", "", normalized)
        return normalized

    def generate_plexmatch_all(
        self,
        media_root: str,
        library: str = "",
        ordering_id: str | None = None,
        *,
        append: bool = False,
    ) -> PlexMatchBatchResult:
        """Generate .plexmatch files for all series in a media directory.

        Scans the media directory for series folders, matches each to a
        Shoko series by name, and writes .plexmatch files for all matches.
        Skips directories that don't match any Shoko series.

        Handles multi-series TMDB grouping: when multiple Shoko series
        share the same TMDB show ID (e.g. Spy x Family has separate
        entries per cour), they are combined into a single .plexmatch
        with proper season/episode numbering.

        Uses the ordering preference cache (set via 'plexmatch-prefer') to
        select the correct TMDB episode ordering for each show. When an
        explicit ordering_id is provided, it takes priority over cached
        preferences. Shows without a stored preference use Shoko's default
        TMDB mapping (no alternate ordering).

        Args:
            media_root: Root path of the media library (e.g. '/mnt/nfs/media').
            library: Subdirectory within media_root (e.g. 'anime').
            ordering_id: TMDB episode ordering ID to apply to ALL series.
                When provided, overrides the per-show preference cache.
                When None (the default), uses the preference cache for each
                show individually.
            append: If True and a .plexmatch file already exists in a target
                directory, merge existing entries with new ones (new entries
                override duplicates by season/episode key).

        Returns:
            PlexMatchBatchResult with per-series success/failure details.
        """
        from pathlib import Path

        from plexctl.ordering_cache import get_ordering_preference

        scan_dir = Path(media_root) / library if library else Path(media_root)

        if not scan_dir.is_dir():
            return PlexMatchBatchResult(
                total_dirs=0,
                results=[],
                failed=1,
            )

        # Collect all subdirectories that look like series dirs
        series_dirs = [
            entry
            for entry in sorted(scan_dir.iterdir())
            if entry.is_dir() and not entry.name.startswith(".")
        ]

        if not series_dirs:
            return PlexMatchBatchResult(
                total_dirs=0,
                results=[],
            )

        # Fetch all Shoko series and build lookup tables
        all_shoko_series: list[ShokoSeries] = []
        page = 1
        total = None
        while total is None or len(all_shoko_series) < total:
            series_page, total = self.list_series(
                page=page,
                page_size=_DEFAULT_PAGE_SIZE,
            )
            if not series_page:
                break
            all_shoko_series.extend(series_page)
            page += 1
            if page > (total // _DEFAULT_PAGE_SIZE) + 2:
                break

        # Build lookup: normalized_name -> list of ShokoSeries (may match multiple)
        name_to_series_list: dict[str, list[ShokoSeries]] = {}
        for s in all_shoko_series:
            key = self._normalize_name(s.name or "")
            if key:
                name_to_series_list.setdefault(key, []).append(s)

        # Build lookup: tmdb_show_id -> list of ShokoSeries (for grouped series)
        tmdb_to_series: dict[int, list[ShokoSeries]] = {}
        for s in all_shoko_series:
            for show_tmdb_id in s.ids.tmdb_show:
                tmdb_to_series.setdefault(show_tmdb_id, []).append(s)

        # Process each directory
        results: list[PlexMatchResult] = []
        seen_tmdb_groups: set[int] = set()

        for dir_path in series_dirs:
            folder_name = dir_path.name
            normalized_folder = self._normalize_name(folder_name)

            # Find matching Shoko series
            matched_series_list = name_to_series_list.get(normalized_folder, [])

            if not matched_series_list:
                # Try substring matching as fallback
                for key, series_list in name_to_series_list.items():
                    if key in normalized_folder or normalized_folder in key:
                        matched_series_list = series_list
                        break

            if not matched_series_list:
                results.append(
                    PlexMatchResult(
                        series_id=0,
                        series_name="",
                        folder_name=folder_name,
                        folder_path=str(dir_path),
                        success=False,
                        error="No matching Shoko series found",
                    )
                )
                continue

            # Use the first matched series
            primary_series = matched_series_list[0]
            target_dir = dir_path
            title_series = primary_series

            # Check if this series shares a TMDB show with other series
            tmdb_id: int | None = (
                primary_series.ids.tmdb_show[0]
                if primary_series.ids.tmdb_show
                else None
            )
            combined_ids: list[int] = [primary_series.ids.id]

            if tmdb_id:
                # Skip this directory if we've already processed its TMDB group
                if tmdb_id in seen_tmdb_groups:
                    continue
                seen_tmdb_groups.add(tmdb_id)

                # Find all series sharing this TMDB show ID
                group = tmdb_to_series.get(tmdb_id, [])
                combined_ids = [s.ids.id for s in group]

                # Use the title from the series that has the most local episodes
                # (typically the base/first season)
                if len(group) > 1:
                    title_series = max(group, key=lambda s: s.local_sizes.episodes)

                # Check if subdirectories match the other series in the group
                # If so, write .plexmatch to the parent directory
                has_subs = any(
                    (dir_path / s.name).is_dir()
                    or (dir_path / s.name.rstrip(")")).is_dir()
                    for s in group
                )
                if not has_subs:
                    # Check if any subdirectory of this dir matches a group series
                    sub_names = {
                        self._normalize_name(d.name)
                        for d in dir_path.iterdir()
                        if d.is_dir()
                    }
                    for s in group:
                        if self._normalize_name(s.name or "") in sub_names:
                            has_subs = True
                            break

                # If the directory contains subdirs for each series, use parent dir
                if has_subs:
                    target_dir = dir_path

            else:
                title_series = primary_series

            # Generate .plexmatch (combined if multiple series)
            try:
                plexmatch_dir_name = target_dir.name
                # Resolve ordering: explicit CLI flag > per-show cache > None
                resolved_ordering_id = ordering_id
                if not resolved_ordering_id and tmdb_id:
                    resolved_ordering_id = get_ordering_preference(tmdb_id)
                if len(combined_ids) > 1:
                    plexmatch = self.generate_plexmatch_combined(
                        combined_ids,
                        title=title_series.name,
                        plexmatch_dir=plexmatch_dir_name,
                        ordering_id=resolved_ordering_id,
                        append=append,
                        append_dir=str(target_dir),
                    )
                else:
                    plexmatch = self.generate_plexmatch(
                        combined_ids[0],
                        plexmatch_dir=plexmatch_dir_name,
                        ordering_id=resolved_ordering_id,
                        append=append,
                        append_dir=str(target_dir),
                    )

                content = plexmatch.render()

                # Write to directory
                plexmatch_path = target_dir / ".plexmatch"
                plexmatch_path.write_text(content, encoding="utf-8")

                results.append(
                    PlexMatchResult(
                        series_id=primary_series.ids.id,
                        series_name=title_series.name or "",
                        folder_name=folder_name,
                        folder_path=str(target_dir),
                        success=True,
                        entry_count=len(plexmatch.entries),
                    )
                )
            except Exception as exc:
                results.append(
                    PlexMatchResult(
                        series_id=primary_series.ids.id,
                        series_name=primary_series.name or "",
                        folder_name=folder_name,
                        folder_path=str(target_dir),
                        success=False,
                        error=str(exc),
                    )
                )

        matched = sum(1 for r in results if r.series_id > 0)
        generated = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success and r.series_id > 0)
        skipped = sum(1 for r in results if r.series_id == 0)

        return PlexMatchBatchResult(
            total_dirs=len(series_dirs),
            matched=matched,
            generated=generated,
            failed=failed,
            skipped=skipped,
            results=results,
        )

    # --- Triage helpers ------------------------------------------------------

    def triage_section(
        self,
        section_title: str = "Anime",
        path_map: dict[str, str] | None = None,
    ) -> TriageReport:
        """Cross-reference all data sources for a library section.

        Args:
            section_title: Name of the Plex library section to triage.
            path_map: Mapping of server paths to local paths
                (e.g. {"/data": "/mnt/nfs/media"}).

        Returns:
            TriageReport with all detected issues and recommendations.
        """
        issues: list[TriageIssue] = []

        # Collect data from all three sources
        plex_issues = self._collect_plex_issues(section_title)
        shoko_issues = self._collect_shoko_issues()
        fs_issues = self._collect_filesystem_issues(section_title, path_map)

        issues.extend(plex_issues)
        issues.extend(shoko_issues)
        issues.extend(fs_issues)

        # Cross-reference: match Shoko series to Plex shows
        self._cross_reference(issues)

        total_shows = self._count_shows(section_title)
        summary = self._build_summary(issues, section_title, total_shows)

        return TriageReport(
            section_title=section_title,
            total_shows=total_shows,
            issues=issues,
            summary=summary,
        )

    def _collect_shoko_issues(self) -> list[TriageIssue]:
        """Collect issues from Shoko data.

        Delegates to ShokoService.collect_triage_issues() which converts
        Shoko mismatches into TriageIssue objects. Returns empty list
        if no ShokoService is available.
        """
        if self._shoko_service is None:
            return []
        return self._shoko_service.collect_triage_issues()

    def _collect_filesystem_issues(
        self,
        section_title: str,
        path_map: dict[str, str] | None,
    ) -> list[TriageIssue]:
        """Collect issues from filesystem comparison."""
        from plexctl.services.fs_compare import FsCompareService

        issues: list[TriageIssue] = []
        fs = FsCompareService(self._plex_client, path_map=path_map)
        result = fs.compare_section(section_title)

        # Grouping risk directories
        for d in result.grouped_dirs:
            plex_shows = ", ".join(d.plex_shows) if d.plex_shows else "none"
            issues.append(
                TriageIssue(
                    issue_type=TriageIssueType.GROUPING_RISK,
                    severity=TriageSeverity.WARNING,
                    action=TriageAction.REORGANIZE,
                    detail=(
                        f"Directory has both files and {d.subdir_count} subdirs "
                        f"(ShokoRelay will split): {d.subdirs}"
                    ),
                    paths=[d.path],
                    plex_title=plex_shows if d.plex_shows else None,
                )
            )

        # Multi-location shows
        for show_title, locations in result.multi_location_shows:
            issues.append(
                TriageIssue(
                    issue_type=TriageIssueType.MULTI_LOCATION,
                    severity=TriageSeverity.WARNING,
                    action=TriageAction.SHOKO_CONFIG,
                    detail=(
                        f"Plex show references {len(locations)} filesystem directories "
                        f"(Shoko merged multiple AniDB entries)"
                    ),
                    paths=locations,
                    plex_title=show_title,
                )
            )

        return issues

    def _cross_reference(self, issues: list[TriageIssue]) -> None:
        """Match Shoko series to Plex shows by name for cross-reference.

        Enriches Shoko issues with plex_key when a matching Plex show
        is found in the issue list.
        """
        plex_by_title: dict[str, str] = {}
        for issue in issues:
            if issue.plex_title and issue.plex_key:
                plex_by_title[issue.plex_title.lower()] = issue.plex_key

        for issue in issues:
            if issue.shoko_name and not issue.plex_key:
                # Try exact match first
                lower_name = issue.shoko_name.lower()
                if lower_name in plex_by_title:
                    issue.plex_key = plex_by_title[lower_name]
                    issue.plex_title = issue.shoko_name
                    continue

                # Try partial match (Shoko names are often shorter)
                for plex_title_lower, plex_key in plex_by_title.items():
                    if lower_name in plex_title_lower or plex_title_lower in lower_name:
                        issue.plex_key = plex_key
                        issue.plex_title = plex_title_lower.title()
                        break

    def _count_shows(self, section_title: str) -> int:
        """Count total shows in a section."""
        from plexctl.services.metadata import MetadataService

        meta = MetadataService(self._plex_client)
        sections = meta.list_sections()
        for s in sections:
            if s.title == section_title:
                return s.count
        return 0

    def find_season_gaps(self, section_title: str = "Anime") -> SeasonGapReport:
        """Cross-reference Shoko series with Plex to find missing seasons.

        Groups Shoko series by TMDB show ID, then matches each group to
        a Plex show and compares expected episodes vs actual.

        Args:
            section_title: Name of the Plex library section to analyze.

        Returns:
            SeasonGapReport with all detected gaps.

        Raises:
            ValueError: If no ShokoService is configured.
        """
        if self._shoko_service is None:
            msg = "ShokoService is required for season gap analysis"
            raise ValueError(msg)

        # Collect all Shoko series grouped by TMDB show ID
        shoko_by_tmdb = self._shoko_service.group_series_by_tmdb()
        all_shoko = self._shoko_service.series_name_dict()

        # Get Plex shows with their season structure
        plex_shows = self._collect_plex_seasons(section_title)

        # Match Shoko groups to Plex shows
        gaps: list[SeasonGap] = []
        matched_plex_keys: set[str] = set()

        for tmdb_id, shoko_series in shoko_by_tmdb.items():
            gap = self._match_group_to_plex(
                tmdb_id=tmdb_id,
                shoko_series=shoko_series,
                plex_shows=plex_shows,
                all_shoko=all_shoko,
            )
            if gap is not None:
                gaps.append(gap)
                if gap.plex_key:
                    matched_plex_keys.add(gap.plex_key)

        # Add Plex shows not matched to any Shoko TMDB group
        for key, show_data in plex_shows.items():
            if key not in matched_plex_keys:
                gap = SeasonGap(
                    plex_title=show_data["title"],
                    plex_key=key,
                    plex_seasons=[
                        PlexSeasonEntry(
                            season_number=s["number"],
                            title=s["title"],
                            episode_count=s["episodes"],
                        )
                        for s in show_data["seasons"]
                    ],
                    actual_episode_count=show_data["total_episodes"],
                    is_missing=False,
                )
                gaps.append(gap)

        # Sort by episode deficit (largest gap first)
        gaps.sort(
            key=lambda g: g.expected_episode_count - g.actual_episode_count,
            reverse=True,
        )

        # Count shows with actual gaps
        gap_count = sum(1 for g in gaps if g.is_missing)

        summary = self._build_gap_summary(
            section_title, len(plex_shows), gap_count, gaps
        )
        return SeasonGapReport(
            section_title=section_title,
            total_shows=len(plex_shows),
            gap_count=gap_count,
            gaps=gaps,
            summary=summary,
        )

    def collect_triage_issues(self) -> list[TriageIssue]:
        """Collect triage issues from Shoko data.

        Queries Shoko for problem series and converts each mismatch
        into a TriageIssue suitable for the unified triage report.

        Returns:
            List of TriageIssue objects with Shoko-specific issue types.
        """
        mismatches = self.find_problem_series()
        issues: list[TriageIssue] = []

        for m in mismatches:
            if m.mismatch_type == "no_local_episodes":
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.NO_LOCAL_EPISODES,
                        severity=TriageSeverity.ERROR,
                        action=TriageAction.SHOKO_CONFIG,
                        shoko_id=m.shoko_id,
                        shoko_name=m.name,
                        detail=m.detail,
                    )
                )
            elif m.mismatch_type == "no_tmdb_link":
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.NO_TMDB_LINK,
                        severity=TriageSeverity.WARNING,
                        action=TriageAction.LINK_TMDB,
                        shoko_id=m.shoko_id,
                        shoko_name=m.name,
                        detail=m.detail,
                    )
                )
            elif m.mismatch_type == "multiple_tmdb_links":
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.MULTIPLE_TMDB_LINKS,
                        severity=TriageSeverity.INFO,
                        action=TriageAction.SHOKO_CONFIG,
                        shoko_id=m.shoko_id,
                        shoko_name=m.name,
                        detail=m.detail,
                    )
                )

        return issues

    def group_series_by_tmdb(self) -> dict[int, list[ShokoSeasonEntry]]:
        """Group Shoko series by TMDB show ID for season gap analysis.

        Returns:
            Dict mapping TMDB show ID to list of ShokoSeasonEntry objects.
            Series without TMDB links are excluded.
        """
        grouped: dict[int, list[ShokoSeasonEntry]] = {}
        all_series = self.list_series()

        for series in all_series[0]:
            if not series.ids.tmdb_show:
                continue
            for tmdb_id in series.ids.tmdb_show:
                entry = ShokoSeasonEntry(
                    shoko_id=series.ids.id,
                    name=series.name,
                    anidb_id=series.ids.anidb or 0,
                    episode_count=series.episode_count,
                )
                if tmdb_id not in grouped:
                    grouped[tmdb_id] = []
                grouped[tmdb_id].append(entry)

        return grouped

    def series_name_dict(self) -> dict[str, Any]:
        """Return a lowercase-name→series dict for cross-referencing.

        Returns:
            Dict mapping lowercased series name to ShokoSeries object.
        """
        all_series = self.list_series()
        return {s.name.lower(): s for s in all_series[0]}
