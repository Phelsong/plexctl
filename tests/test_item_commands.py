"""CLI-level integration tests for the 'item' command group."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from plexctl.cli import app
from plexctl.config import PlexConfig
from plexctl.models import FixResult, MatchResult, MediaMetadata, MediaType, SearchResult
from plexctl.services.fixes import FixService
from plexctl.services.metadata import MetadataService
from plexctl.services.search import SearchService
from plexctl.services.server import ServerService

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared patch helpers
# ---------------------------------------------------------------------------

# Patch targets live in plexctl.commands.item because that's where
# load_config and PlexClient are imported and called.

CONFIG_PATCH = "plexctl.commands.item.load_config"
CLIENT_PATCH = "plexctl.commands.item.PlexClient"

MOCK_CONFIG = PlexConfig(url="http://localhost:32400", token="test-token")


def _patch_item_service(service_cls: type, method: str, return_value):
    """Return a patch.object context for a service method."""
    return patch.object(service_cls, method, return_value=return_value)


# ---------------------------------------------------------------------------
# item delete
# ---------------------------------------------------------------------------


class TestItemDeleteCommand:
    """Tests for 'plexctl item delete' CLI command."""

    def test_item_delete_requires_confirmation(self) -> None:
        """item delete without --yes exits with code 1 and shows confirmation
        message."""
        result = runner.invoke(app, ["item", "delete", "12345"])
        assert result.exit_code == 1
        assert "yes" in result.output.lower() or "confirm" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_delete_with_confirmation(self, mock_config, mock_client_cls) -> None:
        """item delete --yes calls ServerService.delete_item."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        success_result = FixResult(key="12345", action="delete", success=True)

        with _patch_item_service(ServerService, "delete_item", success_result):
            result = runner.invoke(app, ["item", "delete", "12345", "--yes"])

        assert result.exit_code == 0
        assert "12345" in result.output


# ---------------------------------------------------------------------------
# item info
# ---------------------------------------------------------------------------


class TestItemInfoCommand:
    """Tests for 'plexctl item info' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_info_displays_metadata(self, mock_config, mock_client_cls) -> None:
        """item info calls MetadataService.get_metadata and displays result."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        metadata = MediaMetadata(
            key="12345",
            title="Test Movie",
            media_type=MediaType.MOVIE,
            year=2024,
            rating=8.5,
            studio="Test Studio",
            summary="A test summary.",
        )

        with _patch_item_service(MetadataService, "get_metadata", metadata):
            result = runner.invoke(app, ["item", "info", "12345"])

        assert result.exit_code == 0
        assert "Test Movie" in result.output
        assert "12345" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_info_not_found(self, mock_config, mock_client_cls) -> None:
        """item info shows message when item is not found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with _patch_item_service(MetadataService, "get_metadata", None):
            result = runner.invoke(app, ["item", "info", "99999"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "unsupported" in result.output.lower()


# ---------------------------------------------------------------------------
# item search
# ---------------------------------------------------------------------------


class TestItemSearchCommand:
    """Tests for 'plexctl item search' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_search_with_results(self, mock_config, mock_client_cls) -> None:
        """item search calls MetadataService.search and displays results."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        results = [
            MediaMetadata(key="1", title="Big Buck Bunny", media_type=MediaType.MOVIE, year=2008)
        ]

        with _patch_item_service(MetadataService, "search", results):
            result = runner.invoke(app, ["item", "search", "Bunny"])

        assert result.exit_code == 0
        assert "Bunny" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_search_no_results(self, mock_config, mock_client_cls) -> None:
        """item search shows message when no results found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with _patch_item_service(MetadataService, "search", []):
            result = runner.invoke(app, ["item", "search", "nonexistent"])

        assert result.exit_code == 0
        assert "no results" in result.output.lower()


# ---------------------------------------------------------------------------
# item edit
# ---------------------------------------------------------------------------


class TestItemEditCommand:
    """Tests for 'plexctl item edit' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_edit_calls_service(self, mock_config, mock_client_cls) -> None:
        """item edit calls MetadataService.edit_metadata with correct args."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        updated = MediaMetadata(key="12345", title="Updated Title", media_type=MediaType.MOVIE)

        with patch.object(MetadataService, "edit_metadata", return_value=updated) as mock_edit:
            result = runner.invoke(app, ["item", "edit", "12345", "title", "Updated Title"])

        assert result.exit_code == 0
        assert "Updated" in result.output or "title" in result.output.lower()
        mock_edit.assert_called_once()
        edit_args = mock_edit.call_args
        assert edit_args[0][0] == "12345"
        edits = edit_args[0][1]
        assert len(edits) == 1
        assert edits[0].field == "title"
        assert edits[0].value == "Updated Title"


# ---------------------------------------------------------------------------
# item rate
# ---------------------------------------------------------------------------


class TestItemRateCommand:
    """Tests for 'plexctl item rate' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_rate_calls_service(self, mock_config, mock_client_cls) -> None:
        """item rate calls ServerService.rate with correct args."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        rate_result = FixResult(key="12345", action="rate", success=True)

        with patch.object(ServerService, "rate", return_value=rate_result) as mock_rate:
            result = runner.invoke(app, ["item", "rate", "12345", "8.5"])

        assert result.exit_code == 0
        mock_rate.assert_called_once_with("12345", 8.5)

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_rate_failure(self, mock_config, mock_client_cls) -> None:
        """item rate shows error when service returns failure."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        rate_result = FixResult(key="12345", action="rate", success=False, error="server error")

        with patch.object(ServerService, "rate", return_value=rate_result):
            result = runner.invoke(app, ["item", "rate", "12345", "8.5"])

        assert result.exit_code == 0
        assert "failed" in result.output.lower() or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# item watch / item unwatch
# ---------------------------------------------------------------------------


class TestItemWatchCommand:
    """Tests for 'plexctl item watch' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_watch_calls_scrobble(self, mock_config, mock_client_cls) -> None:
        """item watch calls ServerService.scrobble."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        scrobble_result = FixResult(key="12345", action="scrobble", success=True)

        with patch.object(
            ServerService, "scrobble", return_value=scrobble_result
        ) as mock_scrobble:
            result = runner.invoke(app, ["item", "watch", "12345"])

        assert result.exit_code == 0
        mock_scrobble.assert_called_once_with("12345")
        assert "watched" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_unwatch_calls_unscrobble(self, mock_config, mock_client_cls) -> None:
        """item unwatch calls ServerService.unscrobble."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        unscrobble_result = FixResult(key="12345", action="unscrobble", success=True)

        with patch.object(
            ServerService, "unscrobble", return_value=unscrobble_result
        ) as mock_unscrobble:
            result = runner.invoke(app, ["item", "unwatch", "12345"])

        assert result.exit_code == 0
        mock_unscrobble.assert_called_once_with("12345")
        assert "unwatched" in result.output.lower()


# ---------------------------------------------------------------------------
# item ingest
# ---------------------------------------------------------------------------


class TestItemIngestCommand:
    """Tests for 'plexctl item ingest' CLI command."""

    def test_item_ingest_list_shows_models(self) -> None:
        """item ingest list shows available model names — no mocking needed."""
        result = runner.invoke(app, ["item", "ingest", "list"])
        assert result.exit_code == 0
        assert "available" in result.output.lower() or "model" in result.output.lower()

    def test_item_ingest_unknown_model_fails(self) -> None:
        """item ingest with an unknown model name exits with error."""
        result = runner.invoke(app, ["item", "ingest", "completely_fake_model", "/tmp/fake.csv"])
        assert result.exit_code == 1
        assert "unknown model" in result.output.lower()


# ---------------------------------------------------------------------------
# item matches
# ---------------------------------------------------------------------------


class TestItemMatchesCommand:
    """Tests for 'plexctl item matches' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_matches_with_results(self, mock_config, mock_client_cls) -> None:
        """item matches calls FixService.find_matches and displays results."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        matches = [
            MatchResult(name="Correct Show", score=100, year="2024", guid="tvdb://12345"),
            MatchResult(name="Wrong Show", score=50, year="2020", guid="tvdb://67890"),
        ]

        with patch.object(FixService, "find_matches", return_value=matches) as mock_find:
            result = runner.invoke(app, ["item", "matches", "12345"])

        assert result.exit_code == 0
        mock_find.assert_called_once_with("12345", agent=None, title=None, year=None)
        assert "Correct Show" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_matches_no_results(self, mock_config, mock_client_cls) -> None:
        """item matches shows message when no matches found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(FixService, "find_matches", return_value=[]):
            result = runner.invoke(app, ["item", "matches", "12345"])

        assert result.exit_code == 0
        assert "no matches" in result.output.lower()


# ---------------------------------------------------------------------------
# item fix-match
# ---------------------------------------------------------------------------


class TestItemFixMatchCommand:
    """Tests for 'plexctl item fix-match' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_fix_match_calls_service(self, mock_config, mock_client_cls) -> None:
        """item fix-match calls FixService.fix_match with correct args."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fix_result = FixResult(
            key="12345",
            title="Test Show",
            action="fix-match",
            matched_to="Correct Show",
            success=True,
        )

        with patch.object(FixService, "fix_match", return_value=fix_result) as mock_fix:
            result = runner.invoke(app, ["item", "fix-match", "12345"])

        assert result.exit_code == 0
        mock_fix.assert_called_once_with(
            "12345", match_index=0, agent=None, title=None, year=None
        )
        assert (
            "Fixed" in result.output or "fixed" in result.output.lower() or "✓" in result.output
        )

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_fix_match_with_options(self, mock_config, mock_client_cls) -> None:
        """item fix-match passes agent, title, year options to service."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fix_result = FixResult(
            key="12345",
            title="Test Show",
            action="fix-match",
            matched_to="Correct Show",
            success=True,
        )

        with patch.object(FixService, "fix_match", return_value=fix_result) as mock_fix:
            result = runner.invoke(
                app,
                [
                    "item",
                    "fix-match",
                    "12345",
                    "--match-index",
                    "2",
                    "--agent",
                    "tv.plex.agents.series",
                    "--title",
                    "Override Title",
                    "--year",
                    "2020",
                ],
            )

        assert result.exit_code == 0
        mock_fix.assert_called_once_with(
            "12345",
            match_index=2,
            agent="tv.plex.agents.series",
            title="Override Title",
            year="2020",
        )

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_fix_match_failure(self, mock_config, mock_client_cls) -> None:
        """item fix-match exits with error when service reports failure."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fix_result = FixResult(
            key="12345",
            title="Test Show",
            action="fix-match",
            success=False,
            error="No matches found",
        )

        with patch.object(FixService, "fix_match", return_value=fix_result):
            result = runner.invoke(app, ["item", "fix-match", "12345"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# item unmatch
# ---------------------------------------------------------------------------


class TestItemUnmatchCommand:
    """Tests for 'plexctl item unmatch' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_unmatch_calls_service(self, mock_config, mock_client_cls) -> None:
        """item unmatch calls FixService.unmatch."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        unmatch_result = FixResult(key="12345", title="Test Show", action="unmatch", success=True)

        with patch.object(FixService, "unmatch", return_value=unmatch_result) as mock_unmatch:
            result = runner.invoke(app, ["item", "unmatch", "12345"])

        assert result.exit_code == 0
        mock_unmatch.assert_called_once_with("12345")
        assert "unmatch" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_unmatch_failure(self, mock_config, mock_client_cls) -> None:
        """item unmatch exits with error when service reports failure."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        unmatch_result = FixResult(
            key="12345",
            title="Test Show",
            action="unmatch",
            success=False,
            error="Item not found",
        )

        with patch.object(FixService, "unmatch", return_value=unmatch_result):
            result = runner.invoke(app, ["item", "unmatch", "12345"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# item get
# ---------------------------------------------------------------------------


class TestItemGetCommand:
    """Tests for 'plexctl item get' CLI command."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_get_found(self, mock_config, mock_client_cls) -> None:
        """item get calls SearchService.search_by_key and displays result."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        search_result = SearchResult(
            key="12345",
            title="Test Movie",
            media_type=MediaType.MOVIE,
            year=2024,
            rating=9.1,
            section_title="Movies",
        )

        with patch.object(SearchService, "search_by_key", return_value=search_result):
            result = runner.invoke(app, ["item", "get", "12345"])

        assert result.exit_code == 0
        assert "Test Movie" in result.output
        assert "12345" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_item_get_not_found(self, mock_config, mock_client_cls) -> None:
        """item get exits with error when key is not found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(SearchService, "search_by_key", return_value=None):
            result = runner.invoke(app, ["item", "get", "99999"])

        assert result.exit_code == 1
        assert "99999" in result.output
