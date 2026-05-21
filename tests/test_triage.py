"""Tests for triage service and models."""
from __future__ import annotations

from unittest.mock import MagicMock

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


class TestTriageIssueType:
    """Tests for TriageIssueType enum."""

    def test_all_issue_types(self) -> None:
        expected = {
            "unanalyzed",
            "multi_media",
            "missing_files",
            "no_tmdb_link",
            "no_local_episodes",
            "multiple_tmdb_links",
            "grouping_risk",
            "orphan_dir",
            "multi_location",
        }
        actual = {t.value for t in TriageIssueType}
        assert actual == expected

    def test_issue_type_str(self) -> None:
        assert TriageIssueType.UNANALYZED.value == "unanalyzed"
        assert TriageIssueType.GROUPING_RISK.value == "grouping_risk"


class TestTriageSeverity:
    """Tests for TriageSeverity enum."""

    def test_all_severities(self) -> None:
        expected = {"info", "warning", "error", "critical"}
        actual = {s.value for s in TriageSeverity}
        assert actual == expected


class TestTriageAction:
    """Tests for TriageAction enum."""

    def test_all_actions(self) -> None:
        expected = {
            "analyze",
            "refresh",
            "fix-match",
            "link-tmdb",
            "review",
            "reorganize",
            "shoko-config",
        }
        actual = {a.value for a in TriageAction}
        assert actual == expected


class TestTriageIssue:
    """Tests for TriageIssue model."""

    def test_basic_issue(self) -> None:
        issue = TriageIssue(
            issue_type=TriageIssueType.UNANALYZED,
            severity=TriageSeverity.ERROR,
            action=TriageAction.ANALYZE,
            plex_key="61464",
            plex_title="Arifureta",
            detail="31/31 episodes lack codec analysis",
        )
        assert issue.issue_type == TriageIssueType.UNANALYZED
        assert issue.severity == TriageSeverity.ERROR
        assert issue.action == TriageAction.ANALYZE
        assert issue.plex_key == "61464"
        assert issue.shoko_id is None
        assert issue.paths == []

    def test_issue_with_paths(self) -> None:
        issue = TriageIssue(
            issue_type=TriageIssueType.GROUPING_RISK,
            severity=TriageSeverity.WARNING,
            action=TriageAction.REORGANIZE,
            detail="Directory has both files and subdirs",
            paths=["/data/anime/Overlord", "/data/anime/Overlord II"],
        )
        assert len(issue.paths) == 2
        assert "/data/anime/Overlord" in issue.paths

    def test_issue_defaults(self) -> None:
        issue = TriageIssue(
            issue_type=TriageIssueType.MULTI_MEDIA, detail="Multi-media episodes"
        )
        assert issue.severity == TriageSeverity.WARNING
        assert issue.action == TriageAction.REVIEW
        assert issue.plex_key is None
        assert issue.plex_title is None
        assert issue.shoko_id is None
        assert issue.shoko_name is None
        assert issue.paths == []


class TestTriageReport:
    """Tests for TriageReport model."""

    def test_empty_report(self) -> None:
        report = TriageReport()
        assert report.section_title == ""
        assert report.total_shows == 0
        assert report.issues == []
        assert report.summary == ""

    def test_report_with_issues(self) -> None:
        issues = [
            TriageIssue(
                issue_type=TriageIssueType.UNANALYZED,
                severity=TriageSeverity.ERROR,
                action=TriageAction.ANALYZE,
                plex_key="61464",
                plex_title="Arifureta",
                detail="31 episodes unanalyzed",
            ),
            TriageIssue(
                issue_type=TriageIssueType.NO_TMDB_LINK,
                severity=TriageSeverity.WARNING,
                action=TriageAction.LINK_TMDB,
                shoko_id=218,
                shoko_name="Earwig and the Witch",
                detail="No TMDB link",
            ),
        ]
        report = TriageReport(
            section_title="Anime",
            total_shows=51,
            issues=issues,
            summary="2 issues found",
        )
        assert report.section_title == "Anime"
        assert report.total_shows == 51
        assert len(report.issues) == 2


class TestTriageService:
    """Tests for TriageService summary and report logic."""

    def test_build_summary(self) -> None:
        """Test summary generation."""
        from plexctl.services.triage import TriageService

        mock_plex = MagicMock()
        service = TriageService(mock_plex)

        issues = [
            TriageIssue(
                issue_type=TriageIssueType.UNANALYZED,
                severity=TriageSeverity.ERROR,
                action=TriageAction.ANALYZE,
                detail="31 episodes unanalyzed",
            ),
            TriageIssue(
                issue_type=TriageIssueType.UNANALYZED,
                severity=TriageSeverity.ERROR,
                action=TriageAction.ANALYZE,
                detail="12 episodes unanalyzed",
            ),
            TriageIssue(
                issue_type=TriageIssueType.NO_TMDB_LINK,
                severity=TriageSeverity.WARNING,
                action=TriageAction.LINK_TMDB,
                detail="No TMDB link",
            ),
        ]

        summary = service._build_summary(issues, "Anime", 51)
        assert "51 shows" in summary
        assert "3 issues" in summary
        assert "2 errors" in summary
        assert "1 warning" in summary
        assert "analyze: 2" in summary
        assert "link-tmdb: 1" in summary


class TestShokoSeasonEntry:
    """Tests for ShokoSeasonEntry model."""

    def test_basic_entry(self) -> None:
        entry = ShokoSeasonEntry(
            shoko_id=104, name="Spy x Family", anidb_id=16947, episode_count=22
        )
        assert entry.shoko_id == 104
        assert entry.name == "Spy x Family"
        assert entry.anidb_id == 16947
        assert entry.episode_count == 22

    def test_default_episode_count(self) -> None:
        entry = ShokoSeasonEntry(shoko_id=1, name="Test")
        assert entry.episode_count == 0
        assert entry.anidb_id == 0


class TestPlexSeasonEntry:
    """Tests for PlexSeasonEntry model."""

    def test_basic_entry(self) -> None:
        entry = PlexSeasonEntry(season_number=1, title="Season 1", episode_count=13)
        assert entry.season_number == 1
        assert entry.episode_count == 13

    def test_defaults(self) -> None:
        entry = PlexSeasonEntry(season_number=2)
        assert entry.title == ""
        assert entry.episode_count == 0


class TestSeasonGap:
    """Tests for SeasonGap model."""

    def test_basic_gap(self) -> None:
        gap = SeasonGap(
            plex_title="SPY x FAMILY",
            plex_key="12345",
            tmdb_show_id=120089,
            shoko_series=[
                ShokoSeasonEntry(
                    shoko_id=104, name="Spy x Family", anidb_id=16947, episode_count=22
                ),
                ShokoSeasonEntry(
                    shoko_id=102,
                    name="Spy x Family (2022)",
                    anidb_id=17061,
                    episode_count=18,
                ),
            ],
            plex_seasons=[
                PlexSeasonEntry(season_number=1, title="Season 1", episode_count=13)
            ],
            expected_episode_count=40,
            actual_episode_count=13,
            is_missing=True,
        )
        assert gap.plex_title == "SPY x FAMILY"
        assert gap.tmdb_show_id == 120089
        assert len(gap.shoko_series) == 2
        assert len(gap.plex_seasons) == 1
        assert gap.is_missing is True

    def test_no_gap(self) -> None:
        gap = SeasonGap(
            plex_title="Frieren",
            plex_key="999",
            expected_episode_count=28,
            actual_episode_count=28,
            is_missing=False,
        )
        assert gap.is_missing is False
        assert gap.shoko_series == []
        assert gap.plex_seasons == []

    def test_no_plex_match(self) -> None:
        gap = SeasonGap(
            plex_title="New Show (not in Plex)",
            plex_key=None,
            tmdb_show_id=55555,
            shoko_series=[
                ShokoSeasonEntry(shoko_id=50, name="New Show", episode_count=12)
            ],
            expected_episode_count=12,
            actual_episode_count=0,
            is_missing=True,
        )
        assert gap.plex_key is None
        assert gap.actual_episode_count == 0


class TestSeasonGapReport:
    """Tests for SeasonGapReport model."""

    def test_empty_report(self) -> None:
        report = SeasonGapReport()
        assert report.section_title == ""
        assert report.total_shows == 0
        assert report.gap_count == 0
        assert report.gaps == []
        assert report.summary == ""

    def test_report_with_gaps(self) -> None:
        gaps = [
            SeasonGap(
                plex_title="SPY x FAMILY",
                plex_key="123",
                expected_episode_count=77,
                actual_episode_count=13,
                is_missing=True,
            ),
            SeasonGap(
                plex_title="Frieren",
                plex_key="456",
                expected_episode_count=28,
                actual_episode_count=28,
                is_missing=False,
            ),
        ]
        report = SeasonGapReport(
            section_title="Anime",
            total_shows=50,
            gap_count=1,
            gaps=gaps,
            summary="1 gap found",
        )
        assert report.section_title == "Anime"
        assert report.total_shows == 50
        assert report.gap_count == 1
        assert len(report.gaps) == 2


class TestBuildGapSummary:
    """Tests for _build_gap_summary static method."""

    def test_summary_with_gaps(self) -> None:
        from plexctl.services.triage import TriageService

        gaps = [
            SeasonGap(
                plex_title="SPY x FAMILY",
                plex_key="123",
                expected_episode_count=77,
                actual_episode_count=13,
                is_missing=True,
            ),
            SeasonGap(
                plex_title="Overlord",
                plex_key="456",
                expected_episode_count=53,
                actual_episode_count=28,
                is_missing=True,
            ),
        ]
        summary = TriageService._build_gap_summary("Anime", 50, 2, gaps)
        assert "50 Plex shows" in summary
        assert "2 with missing seasons" in summary
        assert "77" in summary
        assert "41" in summary

    def test_summary_no_gaps(self) -> None:
        from plexctl.services.triage import TriageService

        summary = TriageService._build_gap_summary("Anime", 50, 0, [])
        assert "0 with missing seasons" in summary
