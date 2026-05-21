"""Fix service for resolving Plex metadata and matching issues.

Provides methods for finding correct metadata matches, fixing
incorrect matches, refreshing metadata, and triggering library scans.
Also provides batch operations targeting only shows with problems.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plexctl.client import PlexClient

from plexctl.models import BatchFixResult, FixResult, MatchResult

logger = logging.getLogger(__name__)


class FixService:
    """Service for fixing Plex metadata and matching issues.

    Provides methods to:
    - Find metadata matches for incorrectly matched items
    - Apply correct matches to fix wrong metadata
    - Unmatch items from their current metadata
    - Refresh metadata for items or sections
    - Trigger library scans for new files

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def find_matches(
        self,
        rating_key: str | int,
        agent: str | None = None,
        title: str | None = None,
        year: str | None = None,
    ) -> list[MatchResult]:
        """Search for metadata matches for an item.

        Args:
            rating_key: Plex rating key for the show or movie.
            agent: Metadata agent (e.g. 'tv.plex.agents.series').
            title: Override title for the search.
            year: Override year for the search.

        Returns:
            List of MatchResult sorted by score (highest first).
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]

        kwargs: dict[str, object] = {}
        if agent:
            kwargs["agent"] = agent
        if title:
            kwargs["title"] = title
        if year:
            kwargs["year"] = year

        results = item.matches(**kwargs)

        matches = [
            MatchResult(
                name=getattr(r, "name", "Unknown"),
                score=getattr(r, "score", None),
                year=getattr(r, "year", None),
                guid=getattr(r, "guid", None),
            )
            for r in results
        ]

        # Sort by score descending — best match first
        matches.sort(key=lambda m: m.score if m.score is not None else 0, reverse=True)
        return matches

    def fix_match(
        self,
        rating_key: str | int,
        match_index: int = 0,
        agent: str | None = None,
        title: str | None = None,
        year: str | None = None,
    ) -> FixResult:
        """Fix an incorrect match by applying the best (or specified) match.

        Args:
            rating_key: Plex rating key for the item.
            match_index: Which match result to apply (0 = best match).
            agent: Metadata agent for the search.
            title: Override title for the search.
            year: Override year for the search.

        Returns:
            FixResult indicating success or failure.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]

        kwargs: dict[str, object] = {}
        if agent:
            kwargs["agent"] = agent
        if title:
            kwargs["title"] = title
        if year:
            kwargs["year"] = year

        try:
            results = item.matches(**kwargs)
        except Exception as exc:
            return FixResult(
                key=str(key),
                title=getattr(item, "title", None),
                action="fix-match",
                success=False,
                error=str(exc),
            )

        if not results:
            return FixResult(
                key=str(key),
                title=getattr(item, "title", None),
                action="fix-match",
                success=False,
                error="No matches found",
            )

        if match_index >= len(results):
            found = len(results)
            return FixResult(
                key=str(key),
                title=getattr(item, "title", None),
                action="fix-match",
                success=False,
                error=f"Match index {match_index} out of range (found {found} matches)",
            )

        selected = results[match_index]
        try:
            item.fixMatch(searchResult=selected)
        except Exception as exc:
            return FixResult(
                key=str(key),
                title=getattr(item, "title", None),
                action="fix-match",
                matched_to=getattr(selected, "name", None),
                success=False,
                error=str(exc),
            )

        return FixResult(
            key=str(key),
            title=getattr(item, "title", None),
            action="fix-match",
            matched_to=getattr(selected, "name", None),
            success=True,
        )

    def unmatch(self, rating_key: str | int) -> FixResult:
        """Unmatch an item from its current metadata.

        This removes the current metadata association, making the item
        available for rematching with the correct source.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            FixResult indicating success or failure.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        title = getattr(item, "title", None)

        try:
            item.unmatch()
        except Exception as exc:
            return FixResult(
                key=str(key), title=title, action="unmatch", success=False, error=str(exc)
            )

        return FixResult(key=str(key), title=title, action="unmatch", success=True)

    def refresh_item(self, rating_key: str | int) -> FixResult:
        """Refresh metadata for a single item.

        Forces Plex to redownload metadata for the item.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            FixResult indicating success or failure.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        title = getattr(item, "title", None)

        try:
            item.refresh()
        except Exception as exc:
            return FixResult(
                key=str(key), title=title, action="refresh", success=False, error=str(exc)
            )

        return FixResult(key=str(key), title=title, action="refresh", success=True)

    def refresh_section(self, section_title: str) -> FixResult:
        """Refresh metadata for all items in a library section.

        This can take a long time for large libraries.

        Args:
            section_title: Library section name.

        Returns:
            FixResult indicating success or failure.
        """
        section = self._client.server.library.section(section_title)

        try:
            section.refresh()
        except Exception as exc:
            return FixResult(
                key=str(section.key),
                title=section.title,
                action="refresh-section",
                success=False,
                error=str(exc),
            )

        return FixResult(
            key=str(section.key), title=section.title, action="refresh-section", success=True
        )

    def scan_section(self, section_title: str, path: str | None = None) -> FixResult:
        """Scan a library section for new or changed files.

        Args:
            section_title: Library section name.
            path: Optional specific path to scan within the section.

        Returns:
            FixResult indicating success or failure.
        """
        section = self._client.server.library.section(section_title)

        try:
            section.update(path=path)
        except Exception as exc:
            return FixResult(
                key=str(section.key),
                title=section.title,
                action="scan",
                success=False,
                error=str(exc),
            )

        return FixResult(key=str(section.key), title=section.title, action="scan", success=True)

    def batch_analyze(self, section_title: str, only_unanalyzed: bool = True) -> BatchFixResult:
        """Trigger re-analysis for all shows with problems in a section.

        Scans the section for shows with unanalyzed or multi-media episodes,
        then triggers analysis on each. This is much more targeted than
        refreshing the entire section.

        Args:
            section_title: Library section name (e.g. 'Anime').
            only_unanalyzed: If True, only analyze shows with unanalyzed
                episodes. If False, also include shows with multi-media episodes.

        Returns:
            BatchFixResult with per-show outcomes.
        """
        from plexapi.video import Show

        from plexctl.services.diagnostics import DiagnosticService

        # Step 1: Identify problem shows via diagnostics
        diag_service = DiagnosticService(self._client)
        scan = diag_service.scan_section(section_title, deep=False)

        problem_shows = [
            s
            for s in scan.shows
            if (only_unanalyzed and s.unanalyzed_episodes > 0)
            or (not only_unanalyzed and (s.unanalyzed_episodes > 0 or s.multi_media_episodes > 0))
        ]

        if not problem_shows:
            return BatchFixResult()

        # Step 2: Trigger analysis on each problem show
        results: list[FixResult] = []
        succeeded = 0

        for show_diag in problem_shows:
            key = int(show_diag.key)
            try:
                item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
                if isinstance(item, Show):
                    item.analyze()  # type: ignore[no-untyped-call]
                    succeeded += 1
                else:
                    results.append(
                        FixResult(
                            key=str(key),
                            title=show_diag.title,
                            action="batch-analyze",
                            success=False,
                            error=f"Item is {type(item).__name__}, not a Show",
                        )
                    )
            except Exception as exc:
                results.append(
                    FixResult(
                        key=str(key),
                        title=show_diag.title,
                        action="batch-analyze",
                        success=False,
                        error=str(exc),
                    )
                )

        return BatchFixResult(
            total=len(problem_shows), succeeded=succeeded, failed=len(results), results=results
        )

    def batch_refresh(self, section_title: str, only_unanalyzed: bool = True) -> BatchFixResult:
        """Trigger metadata refresh for all shows with problems in a section.

        Similar to batch_analyze but triggers a full metadata refresh
        (redownloads metadata from the agent), which is heavier but
        can fix more issues than analysis alone.

        Args:
            section_title: Library section name (e.g. 'Anime').
            only_unanalyzed: If True, only refresh shows with unanalyzed episodes.

        Returns:
            BatchFixResult with per-show outcomes.
        """
        from plexapi.video import Show

        from plexctl.services.diagnostics import DiagnosticService

        diag_service = DiagnosticService(self._client)
        scan = diag_service.scan_section(section_title, deep=False)

        problem_shows = [
            s
            for s in scan.shows
            if (only_unanalyzed and s.unanalyzed_episodes > 0)
            or (not only_unanalyzed and (s.unanalyzed_episodes > 0 or s.multi_media_episodes > 0))
        ]

        if not problem_shows:
            return BatchFixResult()

        results: list[FixResult] = []
        succeeded = 0

        for show_diag in problem_shows:
            key = int(show_diag.key)
            try:
                item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
                if isinstance(item, Show):
                    item.refresh()  # type: ignore[no-untyped-call]
                    succeeded += 1
                else:
                    results.append(
                        FixResult(
                            key=str(key),
                            title=show_diag.title,
                            action="batch-refresh",
                            success=False,
                            error=f"Item is {type(item).__name__}, not a Show",
                        )
                    )
            except Exception as exc:
                results.append(
                    FixResult(
                        key=str(key),
                        title=show_diag.title,
                        action="batch-refresh",
                        success=False,
                        error=str(exc),
                    )
                )

        return BatchFixResult(
            total=len(problem_shows), succeeded=succeeded, failed=len(results), results=results
        )

    def split_show(self, rating_key: str | int) -> FixResult:
        """Split a multi-location show into separate entries.

        Plex merges shows that reference multiple filesystem locations into
        a single entry. This method splits them back into separate shows,
        allowing each to have its own metadata and season structure.

        Args:
            rating_key: Plex rating key for the show to split.

        Returns:
            FixResult indicating success or failure.
        """
        from plexapi.video import Show

        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        title = getattr(item, "title", None)

        if not isinstance(item, Show):
            return FixResult(
                key=str(key),
                title=title,
                action="split",
                success=False,
                error=f"Item is {type(item).__name__}, not a Show",
            )

        if len(getattr(item, "locations", [])) <= 1:
            return FixResult(
                key=str(key),
                title=title,
                action="split",
                success=False,
                error="Show has only one location, nothing to split",
            )

        try:
            item.split()  # type: ignore[no-untyped-call]
        except Exception as exc:
            return FixResult(
                key=str(key), title=title, action="split", success=False, error=str(exc)
            )

        locations = getattr(item, "locations", [])
        return FixResult(
            key=str(key),
            title=title,
            action="split",
            matched_to=f"Split into {len(locations)} shows",
            success=True,
        )

    def remove_duplicate_media(self, section_title: str, dry_run: bool = True) -> BatchFixResult:
        """Remove duplicate media versions from episodes in a section.

        Scans all shows in a section for episodes with multiple media
        versions. For each such episode, keeps the first media version
        (which is typically the best quality) and deletes the rest.

        This is a destructive operation — use dry_run=True first to
        review what would be deleted.

        Args:
            section_title: Library section name (e.g. 'Anime').
            dry_run: If True, only report what would be deleted without
                actually deleting. Defaults to True for safety.

        Returns:
            BatchFixResult with per-episode outcomes.
        """
        section = self._client.server.library.section(section_title)
        results: list[FixResult] = []
        succeeded = 0

        for show in section.search():
            for season in show.seasons():
                for episode in season.episodes():
                    media_list = episode.media
                    if not isinstance(media_list, list) or len(media_list) <= 1:
                        continue

                    episode_title = getattr(episode, "title", "Unknown")
                    show_title = getattr(show, "title", "?")

                    # Keep the first media version, delete the rest
                    for media in media_list[1:]:
                        if dry_run:
                            results.append(
                                FixResult(
                                    key=str(getattr(episode, "ratingKey", "")),
                                    title=f"{show_title} - {episode_title}",
                                    action="remove-duplicate (dry-run)",
                                    success=True,
                                )
                            )
                            succeeded += 1
                        else:
                            try:
                                media.delete()
                                succeeded += 1
                            except Exception as exc:
                                results.append(
                                    FixResult(
                                        key=str(getattr(episode, "ratingKey", "")),
                                        title=f"{show_title} - {episode_title}",
                                        action="remove-duplicate",
                                        success=False,
                                        error=str(exc),
                                    )
                                )

        return BatchFixResult(
            total=succeeded + len(results),
            succeeded=succeeded,
            failed=len([r for r in results if not r.success]),
            results=results,
        )
