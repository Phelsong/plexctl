"""Tests for FixService and match/fix models."""
from __future__ import annotations

from unittest.mock import MagicMock

from plexctl.models import BatchFixResult, FixResult, MatchResult
from plexctl.services.fixes import FixService


class TestMatchResult:
    """Tests for MatchResult model."""

    def test_match_result_creation(self) -> None:
        result = MatchResult(
            name="Arifureta", score=95, year="2019", guid="plex://show/abc123"
        )
        assert result.name == "Arifureta"
        assert result.score == 95
        assert result.year == "2019"
        assert result.guid == "plex://show/abc123"

    def test_match_result_defaults(self) -> None:
        result = MatchResult(name="Test Show")
        assert result.score is None
        assert result.year is None
        assert result.guid is None


class TestFixResult:
    """Tests for FixResult model."""

    def test_fix_result_success(self) -> None:
        result = FixResult(
            key="12345",
            title="Test Show",
            action="fix-match",
            matched_to="Correct Match",
            success=True,
        )
        assert result.key == "12345"
        assert result.title == "Test Show"
        assert result.action == "fix-match"
        assert result.matched_to == "Correct Match"
        assert result.success is True
        assert result.error is None

    def test_fix_result_failure(self) -> None:
        result = FixResult(
            key="12345",
            title="Test Show",
            action="unmatch",
            success=False,
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"

    def test_fix_result_defaults(self) -> None:
        result = FixResult(key="12345")
        assert result.title is None
        assert result.action == ""
        assert result.matched_to is None
        assert result.success is True
        assert result.error is None


class TestFixServiceFindMatches:
    """Tests for FixService.find_matches."""

    def test_find_matches_returns_sorted_results(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item

        match1 = MagicMock()
        match1.name = "Low Score Show"
        match1.score = 50
        match1.year = "2020"
        match1.guid = "guid1"

        match2 = MagicMock()
        match2.name = "High Score Show"
        match2.score = 99
        match2.year = "2019"
        match2.guid = "guid2"

        mock_item.matches.return_value = [match1, match2]

        service = FixService(mock_client)
        results = service.find_matches("12345")

        assert len(results) == 2
        assert results[0].name == "High Score Show"
        assert results[0].score == 99
        assert results[1].name == "Low Score Show"
        assert results[1].score == 50

    def test_find_matches_with_overrides(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.matches.return_value = []

        service = FixService(mock_client)
        service.find_matches(
            "12345", agent="tv.plex.agents.series", title="Arifureta", year="2019"
        )

        mock_item.matches.assert_called_once_with(
            agent="tv.plex.agents.series", title="Arifureta", year="2019"
        )


class TestFixServiceFixMatch:
    """Tests for FixService.fix_match."""

    def test_fix_match_applies_best_match(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item

        match_result = MagicMock()
        match_result.name = "Correct Show"
        mock_item.matches.return_value = [match_result]
        mock_item.title = "Wrong Show"

        service = FixService(mock_client)
        result = service.fix_match("12345")

        assert result.success is True
        assert result.matched_to == "Correct Show"
        assert result.action == "fix-match"
        mock_item.fixMatch.assert_called_once_with(searchResult=match_result)

    def test_fix_match_specific_index(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item

        match0 = MagicMock()
        match0.name = "First Match"
        match1 = MagicMock()
        match1.name = "Second Match"
        mock_item.matches.return_value = [match0, match1]
        mock_item.title = "Test"

        service = FixService(mock_client)
        result = service.fix_match("12345", match_index=1)

        assert result.success is True
        assert result.matched_to == "Second Match"
        mock_item.fixMatch.assert_called_once_with(searchResult=match1)

    def test_fix_match_no_results_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.matches.return_value = []
        mock_item.title = "Test"

        service = FixService(mock_client)
        result = service.fix_match("12345")

        assert result.success is False
        assert result.error == "No matches found"

    def test_fix_match_index_out_of_range(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item

        match = MagicMock()
        match.name = "Only Match"
        mock_item.matches.return_value = [match]
        mock_item.title = "Test"

        service = FixService(mock_client)
        result = service.fix_match("12345", match_index=5)

        assert result.success is False
        assert result.error is not None and "out of range" in result.error

    def test_fix_match_exception_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.matches.side_effect = Exception("Network error")
        mock_item.title = "Test"

        service = FixService(mock_client)
        result = service.fix_match("12345")

        assert result.success is False
        assert result.error == "Network error"

    def test_fix_match_fix_exception_returns_error(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item

        match_result = MagicMock()
        match_result.name = "Match"
        mock_item.matches.return_value = [match_result]
        mock_item.fixMatch.side_effect = Exception("Fix failed")
        mock_item.title = "Test"

        service = FixService(mock_client)
        result = service.fix_match("12345")

        assert result.success is False
        assert result.error == "Fix failed"


class TestFixServiceUnmatch:
    """Tests for FixService.unmatch."""

    def test_unmatch_success(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.title = "Test Show"

        service = FixService(mock_client)
        result = service.unmatch("12345")

        assert result.success is True
        assert result.action == "unmatch"
        assert result.title == "Test Show"
        mock_item.unmatch.assert_called_once()

    def test_unmatch_failure(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.title = "Test Show"
        mock_item.unmatch.side_effect = Exception("Unmatch failed")

        service = FixService(mock_client)
        result = service.unmatch("12345")

        assert result.success is False
        assert result.error == "Unmatch failed"


class TestFixServiceRefresh:
    """Tests for FixService refresh and scan methods."""

    def test_refresh_item_success(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.title = "Test Show"

        service = FixService(mock_client)
        result = service.refresh_item("12345")

        assert result.success is True
        assert result.action == "refresh"
        mock_item.refresh.assert_called_once()

    def test_refresh_item_failure(self) -> None:
        mock_client = MagicMock()
        mock_item = MagicMock()
        mock_client.server.fetchItem.return_value = mock_item
        mock_item.title = "Test Show"
        mock_item.refresh.side_effect = Exception("Refresh failed")

        service = FixService(mock_client)
        result = service.refresh_item("12345")

        assert result.success is False

    def test_refresh_section_success(self) -> None:
        mock_client = MagicMock()
        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_client.server.library.section.return_value = mock_section

        service = FixService(mock_client)
        result = service.refresh_section("Anime")

        assert result.success is True
        assert result.action == "refresh-section"
        mock_section.refresh.assert_called_once()

    def test_scan_section_success(self) -> None:
        mock_client = MagicMock()
        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_client.server.library.section.return_value = mock_section

        service = FixService(mock_client)
        result = service.scan_section("Anime")

        assert result.success is True
        assert result.action == "scan"
        mock_section.update.assert_called_once_with(path=None)

    def test_scan_section_with_path(self) -> None:
        mock_client = MagicMock()
        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_client.server.library.section.return_value = mock_section

        service = FixService(mock_client)
        result = service.scan_section("Anime", path="/data/anime/new")

        assert result.success is True
        mock_section.update.assert_called_once_with(path="/data/anime/new")


class TestBatchFixResult:
    """Tests for BatchFixResult model."""

    def test_batch_fix_result_defaults(self) -> None:
        result = BatchFixResult()
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.results == []

    def test_batch_fix_result_with_failures(self) -> None:
        failure = FixResult(
            key="99",
            title="Broken Show",
            action="batch-analyze",
            success=False,
            error="Connection timeout",
        )
        result = BatchFixResult(total=3, succeeded=2, failed=1, results=[failure])
        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.results) == 1
        assert result.results[0].error == "Connection timeout"


class TestFixServiceBatchAnalyze:
    """Tests for FixService.batch_analyze."""

    def test_batch_analyze_no_problems(self) -> None:
        mock_client = MagicMock()
        # Empty section — no shows with problems
        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_section.type = "show"
        mock_section.scanner = "Shoko Relay Scanner"
        mock_section.agent = "tv.plex.agents.series"
        mock_section.locations = ["/data/anime"]
        mock_section.all.return_value = []
        mock_client.server.library.section.return_value = mock_section

        service = FixService(mock_client)
        result = service.batch_analyze("Anime")

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0

    def test_batch_analyze_with_unanalyzed(self) -> None:
        from plexapi.video import Show

        mock_client = MagicMock()

        # Build minimal show/section mocks for DiagnosticService.scan_section
        mock_episode = MagicMock()
        mock_episode.ratingKey = 200
        mock_episode.title = "Ep 1"
        mock_episode.titleSort = "Ep 1"
        mock_episode.seasonNumber = 1
        mock_episode.index = 1
        mock_episode.media = [MagicMock()]
        mock_episode.media[0].videoCodec = None
        mock_episode.media[0].audioCodec = None
        mock_episode.media[0].container = None
        mock_episode.media[0].parts = []

        mock_season = MagicMock()
        mock_season.episodes.return_value = [mock_episode]

        mock_show = MagicMock(spec=Show)
        mock_show.ratingKey = 100
        mock_show.title = "Test Anime"
        mock_show.year = 2024
        mock_show.locations = ["/data/anime/Test Anime"]
        mock_show.seasons.return_value = [mock_season]

        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_section.type = "show"
        mock_section.scanner = "Shoko Relay Scanner"
        mock_section.agent = "tv.plex.agents.series"
        mock_section.locations = ["/data/anime"]
        mock_section.all.return_value = [mock_show]
        mock_client.server.library.section.return_value = mock_section

        # Mock fetchItem for batch_analyze
        mock_client.server.fetchItem.return_value = mock_show
        mock_show.analyze = MagicMock()

        service = FixService(mock_client)
        result = service.batch_analyze("Anime", only_unanalyzed=True)

        assert result.total == 1
        assert result.succeeded == 1


class TestFixServiceBatchRefresh:
    """Tests for FixService.batch_refresh."""

    def test_batch_refresh_no_problems(self) -> None:
        mock_client = MagicMock()
        mock_section = MagicMock()
        mock_section.key = "22"
        mock_section.title = "Anime"
        mock_section.type = "show"
        mock_section.scanner = "Shoko Relay Scanner"
        mock_section.agent = "tv.plex.agents.series"
        mock_section.locations = ["/data/anime"]
        mock_section.all.return_value = []
        mock_client.server.library.section.return_value = mock_section

        service = FixService(mock_client)
        result = service.batch_refresh("Anime")

        assert result.total == 0
