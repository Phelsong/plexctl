"""Triage service combining Plex and filesystem data.

Cross-references diagnostics from multiple sources to produce a unified
triage report with actionable fix recommendations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plexctl.models import (
    PlexSeasonEntry,
    SeasonGap,
    SeasonGapReport,
    ShokoSeasonEntry,
    TriageAction,
    TriageIssue,
    TriageIssueType,
    TriageReport,
    TriageSeverity,
)

if TYPE_CHECKING:
    from plexctl.client import PlexClient
    from plexctl.plugins.shoko.service import ShokoService

logger = logging.getLogger(__name__)


class TriageService:
    """Service for cross-referencing Plex and filesystem data.

    Combines diagnostics from multiple sources into a unified triage report:

    1. Plex DiagnosticService — unanalyzed media, multi-media episodes
    2. FsCompareService — grouping risks, orphan dirs, multi-location shows

    Args:
        plex_client: Connected PlexClient instance.
        shoko_service: Optional ShokoService for season gap analysis.
    """

    def __init__(
        self,
        plex_client: PlexClient,
        shoko_service: ShokoService | None = None,
    ) -> None:
        self._plex_client = plex_client
        self._shoko_service = shoko_service

    def triage_section(
        self,
        section_title: str = "Movies",
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
        fs_issues = self._collect_filesystem_issues(section_title, path_map)

        issues.extend(plex_issues)
        issues.extend(fs_issues)

        total_shows = self._count_shows(section_title)
        summary = self._build_summary(issues, section_title, total_shows)

        return TriageReport(
            section_title=section_title,
            total_shows=total_shows,
            issues=issues,
            summary=summary,
        )

    def _collect_plex_issues(self, section_title: str) -> list[TriageIssue]:
        """Collect issues from Plex diagnostics for a section."""
        from plexctl.services.diagnostics import DiagnosticService

        issues: list[TriageIssue] = []
        diag = DiagnosticService(self._plex_client)
        section_diag = diag.scan_section(section_title)

        for show in section_diag.shows:
            # Unanalyzed media — can be auto-fixed with batch-analyze
            if show.unanalyzed_episodes > 0:
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.UNANALYZED,
                        severity=TriageSeverity.ERROR,
                        action=TriageAction.ANALYZE,
                        plex_key=show.key,
                        plex_title=show.title or f"key={show.key}",
                        detail=(
                            f"{show.unanalyzed_episodes}/{show.total_episodes} "
                            f"episodes lack codec analysis"
                        ),
                        paths=show.locations,
                    )
                )

            # Multi-media episodes — files from different sources merged
            if show.multi_media_episodes > 0:
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.MULTI_MEDIA,
                        severity=TriageSeverity.WARNING,
                        action=TriageAction.REVIEW,
                        plex_key=show.key,
                        plex_title=show.title or f"key={show.key}",
                        detail=(
                            f"{show.multi_media_episodes} episodes have "
                            f"multiple media versions"
                        ),
                        paths=show.locations,
                    )
                )

            # Missing files
            if show.missing_file_episodes > 0:
                issues.append(
                    TriageIssue(
                        issue_type=TriageIssueType.MISSING_FILES,
                        severity=TriageSeverity.ERROR,
                        action=TriageAction.REVIEW,
                        plex_key=show.key,
                        plex_title=show.title or f"key={show.key}",
                        detail=(
                            f"{show.missing_file_episodes} episodes missing "
                            f"or inaccessible files"
                        ),
                        paths=show.locations,
                    )
                )

        return issues

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
                    detail=(f"Directory has both files and {d.subdir_count} subdirs "),
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
                    ),
                    paths=locations,
                    plex_title=show_title,
                )
            )

        return issues

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

    def _collect_plex_seasons(self, section_title: str) -> dict[str, dict[str, Any]]:
        """Build a dict of Plex shows with their season structure.

        Returns:
            Dict mapping plex rating key to show data dict with:
            title, seasons (list of {number, title, episodes}), total_episodes
        """
        from plexctl.services.metadata import MetadataService

        meta = MetadataService(self._plex_client)
        sections = meta.list_sections()
        section_key = None
        for s in sections:
            if s.title == section_title:
                section_key = s.key
                break

        if not section_key:
            return {}

        server = self._plex_client.server
        section = server.library.sectionByID(int(section_key))
        shows = section.all()

        result: dict[str, dict[str, Any]] = {}
        for show in shows:
            seasons_data = []
            try:
                for season in show.seasons():
                    episode_count = len(season.episodes())
                    seasons_data.append(
                        {
                            "number": season.seasonNumber,
                            "title": season.title or f"Season {season.seasonNumber}",
                            "episodes": episode_count,
                        }
                    )
            except Exception:
                # Some shows may not have accessible seasons
                seasons_data = []

            total_episodes = len(show.episodes()) if hasattr(show, "episodes") else 0
            result[str(show.ratingKey)] = {
                "title": show.title,
                "seasons": seasons_data,
                "total_episodes": total_episodes,
            }

        return result

    def _match_group_to_plex(
        self,
        tmdb_id: int,
        shoko_series: list[ShokoSeasonEntry],
        plex_shows: dict[str, dict[str, Any]],
        all_shoko: dict[str, Any],
    ) -> SeasonGap | None:
        """Match a Shoko TMDB group to a Plex show and compute the gap.

        Args:
            tmdb_id: TMDB show ID.
            shoko_series: List of Shoko series under this TMDB ID.
            plex_shows: Dict of Plex shows from _collect_plex_seasons.
            all_shoko: Dict of all Shoko series by name (lowercase).

        Returns:
            SeasonGap if there are Shoko series, None otherwise.
        """
        if not shoko_series:
            return None

        expected_episode_count = sum(s.episode_count for s in shoko_series)

        # Try to find a Plex show matching this TMDB group
        plex_title = shoko_series[0].name  # Default to first Shoko series name
        plex_key = None
        plex_seasons: list[PlexSeasonEntry] = []
        actual_episode_count = 0

        # Try matching by name
        for key, show_data in plex_shows.items():
            plex_title_lower = show_data["title"].lower()
            for s in shoko_series:
                shoko_name_lower = s.name.lower()
                # Check if names overlap significantly
                if (
                    plex_title_lower == shoko_name_lower
                    or plex_title_lower in shoko_name_lower
                    or shoko_name_lower in plex_title_lower
                ):
                    plex_title = show_data["title"]
                    plex_key = key
                    plex_seasons = [
                        PlexSeasonEntry(
                            season_number=pe["number"],
                            title=pe["title"],
                            episode_count=pe["episodes"],
                        )
                        for pe in show_data["seasons"]
                    ]
                    actual_episode_count = show_data["total_episodes"]
                    break
            if plex_key:
                break

        is_missing = expected_episode_count > actual_episode_count

        return SeasonGap(
            plex_title=plex_title,
            plex_key=plex_key,
            tmdb_show_id=tmdb_id,
            shoko_series=shoko_series,
            plex_seasons=plex_seasons,
            expected_episode_count=expected_episode_count,
            actual_episode_count=actual_episode_count,
            is_missing=is_missing,
        )

    @staticmethod
    def _build_gap_summary(
        section_title: str,
        total_shows: int,
        gap_count: int,
        gaps: list[SeasonGap],
    ) -> str:
        """Build a human-readable summary of the season gap report."""
        total_expected = sum(g.expected_episode_count for g in gaps)
        total_actual = sum(g.actual_episode_count for g in gaps)
        total_deficit = total_expected - total_actual

        lines = [
            f"Section '{section_title}': {total_shows} Plex shows, "
            f"{gap_count} with missing seasons",
            f"  Total expected episodes: {total_expected}",
            f"  Total actual episodes: {total_actual}",
            f"  Missing: {total_deficit} episodes",
        ]

        # Show top gaps
        big_gaps = [g for g in gaps if g.is_missing][:10]
        if big_gaps:
            lines.append("  Top gaps:")
            for g in big_gaps:
                deficit = g.expected_episode_count - g.actual_episode_count
                lines.append(
                    f"    {g.plex_title}: {g.actual_episode_count}/"
                    f"{g.expected_episode_count} eps "
                    f"(missing {deficit})"
                )

        return "\n".join(lines)

    def _build_summary(
        self,
        issues: list[TriageIssue],
        section_title: str,
        total_shows: int,
    ) -> str:
        """Build a human-readable summary of the triage report."""
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_action: dict[str, int] = {}

        for issue in issues:
            by_type[issue.issue_type.value] = by_type.get(issue.issue_type.value, 0) + 1
            by_severity[issue.severity.value] = (
                by_severity.get(issue.severity.value, 0) + 1
            )
            by_action[issue.action.value] = by_action.get(issue.action.value, 0) + 1

        error_count = by_severity.get("error", 0)
        warning_count = by_severity.get("warning", 0)
        info_count = by_severity.get("info", 0)

        lines = [
            f"Section '{section_title}': {total_shows} shows, {len(issues)} issues",
            f"  {error_count} errors, {warning_count} warnings, {info_count} info",
        ]

        if by_type:
            type_lines = [f"    {k}: {v}" for k, v in sorted(by_type.items())]
            lines.append("  Issue breakdown:")
            lines.extend(type_lines)

        if by_action:
            action_lines = [f"    {k}: {v}" for k, v in sorted(by_action.items())]
            lines.append("  Recommended actions:")
            lines.extend(action_lines)

        return "\n".join(lines)
