"""CLI-level integration tests for the 'playlists' command group."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from plexctl.cli import app
from plexctl.config import PlexConfig
from plexctl.models import MediaType, Playlist, PlaylistItem, PlaylistType
from plexctl.services.playlists import PlaylistService

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared patch helpers
# ---------------------------------------------------------------------------

CONFIG_PATCH = "plexctl.commands.playlists.load_config"
CLIENT_PATCH = "plexctl.commands.playlists.PlexClient"

MOCK_CONFIG = PlexConfig(url="http://localhost:32400", token="test-token")


# ---------------------------------------------------------------------------
# playlist list
# ---------------------------------------------------------------------------


class TestPlaylistListCommand:
    """Tests for 'plexctl library playlists list'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_list_playlists_empty(self, mock_config, mock_client_cls) -> None:
        """list shows message when no playlists found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "list_playlists", return_value=[]):
            result = runner.invoke(app, ["library", "playlists", "list"])

        assert result.exit_code == 0
        assert "no regular playlists found" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_list_playlists_with_results(self, mock_config, mock_client_cls) -> None:
        """list displays playlists in a table."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        playlists = [
            Playlist(
                key="100",
                title="My Playlist",
                playlist_type=PlaylistType.VIDEO,
                smart=False,
                item_count=5,
            ),
            Playlist(
                key="200",
                title="Music Mix",
                playlist_type=PlaylistType.AUDIO,
                smart=False,
                item_count=12,
            ),
        ]

        with patch.object(PlaylistService, "list_playlists", return_value=playlists):
            result = runner.invoke(app, ["library", "playlists", "list"])

        assert result.exit_code == 0
        assert "My Playlist" in result.output
        assert "Music Mix" in result.output


# ---------------------------------------------------------------------------
# playlist get
# ---------------------------------------------------------------------------


class TestPlaylistGetCommand:
    """Tests for 'plexctl library playlists get'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_get_existing(self, mock_config, mock_client_cls) -> None:
        """get displays playlist details."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        playlist = Playlist(
            key="12345",
            title="My Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=10,
        )

        with patch.object(PlaylistService, "get_playlist", return_value=playlist):
            result = runner.invoke(app, ["library", "playlists", "get", "12345"])

        assert result.exit_code == 0
        assert "My Playlist" in result.output
        assert "12345" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_get_not_found(self, mock_config, mock_client_cls) -> None:
        """get exits with error when playlist not found."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "get_playlist", return_value=None):
            result = runner.invoke(app, ["library", "playlists", "get", "99999"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# playlist create
# ---------------------------------------------------------------------------


class TestPlaylistCreateCommand:
    """Tests for 'plexctl library playlists create'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_create_playlist(self, mock_config, mock_client_cls) -> None:
        """create calls service and displays success message."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        playlist = Playlist(
            key="500",
            title="New Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=0,
        )

        with patch.object(
            PlaylistService, "create_playlist", return_value=playlist
        ) as mock_create:
            result = runner.invoke(app, ["library", "playlists", "create", "New Playlist"])

        assert result.exit_code == 0
        assert "New Playlist" in result.output
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert (
            call_kwargs[1].get("title") == "New Playlist" or call_kwargs[0][0] == "New Playlist"
        )

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_create_playlist_with_type(self, mock_config, mock_client_cls) -> None:
        """create passes playlist type option."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        playlist = Playlist(
            key="501",
            title="Audio Mix",
            playlist_type=PlaylistType.AUDIO,
            smart=False,
            item_count=0,
        )

        with patch.object(
            PlaylistService, "create_playlist", return_value=playlist
        ) as _mock_create:
            result = runner.invoke(
                app, ["library", "playlists", "create", "Audio Mix", "--type", "audio"]
            )

        assert result.exit_code == 0
        assert "Audio Mix" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_create_playlist_with_items(self, mock_config, mock_client_cls) -> None:
        """create passes item keys to service."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        playlist = Playlist(
            key="502", title="Seeded", playlist_type=PlaylistType.VIDEO, smart=False, item_count=2
        )

        with patch.object(
            PlaylistService, "create_playlist", return_value=playlist
        ) as _mock_create:
            result = runner.invoke(
                app, ["library", "playlists", "create", "Seeded", "-i", "100", "-i", "200"]
            )

        assert result.exit_code == 0
        assert "2 item(s)" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_create_playlist_invalid_type(self, mock_config, mock_client_cls) -> None:
        """create with invalid type exits with error."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(
            app, ["library", "playlists", "create", "Test", "--type", "invalid"]
        )

        assert result.exit_code == 1
        assert "invalid" in result.output.lower()


# ---------------------------------------------------------------------------
# playlist delete
# ---------------------------------------------------------------------------


class TestPlaylistDeleteCommand:
    """Tests for 'plexctl library playlists delete'."""

    def test_delete_requires_confirmation(self) -> None:
        """delete without --yes exits with code 1 and shows confirmation message."""
        result = runner.invoke(app, ["library", "playlists", "delete", "12345"])
        assert result.exit_code == 1
        assert "yes" in result.output.lower() or "confirm" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_delete_with_yes(self, mock_config, mock_client_cls) -> None:
        """delete --yes calls service and shows success."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "delete_playlist") as mock_delete:
            result = runner.invoke(app, ["library", "playlists", "delete", "12345", "--yes"])

        assert result.exit_code == 0
        assert "12345" in result.output
        mock_delete.assert_called_once_with("12345")


# ---------------------------------------------------------------------------
# playlist update
# ---------------------------------------------------------------------------


class TestPlaylistUpdateCommand:
    """Tests for 'plexctl library playlists update'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_update_title(self, mock_config, mock_client_cls) -> None:
        """update changes the title and shows success."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        updated = Playlist(
            key="12345",
            title="New Title",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=5,
        )

        with patch.object(
            PlaylistService, "update_playlist", return_value=updated
        ) as mock_update:
            result = runner.invoke(
                app, ["library", "playlists", "update", "12345", "--title", "New Title"]
            )

        assert result.exit_code == 0
        assert "New Title" in result.output
        mock_update.assert_called_once_with("12345", title="New Title")

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_update_no_title_exits(self, mock_config, mock_client_cls) -> None:
        """update without --title exits with code 1."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["library", "playlists", "update", "12345"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# playlist items
# ---------------------------------------------------------------------------


class TestPlaylistItemsCommand:
    """Tests for 'plexctl library playlists items'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_items_displays_results(self, mock_config, mock_client_cls) -> None:
        """items displays items in a table."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        items = [
            PlaylistItem(
                key="99999",
                title="Some Movie",
                media_type=MediaType.MOVIE,
                year=2023,
                duration=7200000,
            )
        ]

        with patch.object(PlaylistService, "get_playlist_items", return_value=items):
            result = runner.invoke(app, ["library", "playlists", "items", "12345"])

        assert result.exit_code == 0
        assert "Some Movie" in result.output

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_items_empty(self, mock_config, mock_client_cls) -> None:
        """items shows message when playlist is empty."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "get_playlist_items", return_value=[]):
            result = runner.invoke(app, ["library", "playlists", "items", "12345"])

        assert result.exit_code == 0
        assert "no items" in result.output.lower()


# ---------------------------------------------------------------------------
# playlist add
# ---------------------------------------------------------------------------


class TestPlaylistAddCommand:
    """Tests for 'plexctl library playlists add'."""

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_add_items(self, mock_config, mock_client_cls) -> None:
        """add calls service and displays success."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "add_items", return_value=2) as mock_add:
            result = runner.invoke(
                app, ["library", "playlists", "add", "12345", "56789", "56790"]
            )

        assert result.exit_code == 0
        assert "2 item(s)" in result.output
        mock_add.assert_called_once()
        call_args = mock_add.call_args
        assert call_args[0][0] == "12345"
        assert call_args[0][1] == ["56789", "56790"]


# ---------------------------------------------------------------------------
# playlist remove
# ---------------------------------------------------------------------------


class TestPlaylistRemoveCommand:
    """Tests for 'plexctl library playlists remove'."""

    def test_remove_requires_confirmation(self) -> None:
        """remove without --yes exits with code 1."""
        result = runner.invoke(app, ["library", "playlists", "remove", "12345", "56789"])
        assert result.exit_code == 1
        assert "yes" in result.output.lower() or "confirm" in result.output.lower()

    @patch(CLIENT_PATCH)
    @patch(CONFIG_PATCH)
    def test_remove_with_yes(self, mock_config, mock_client_cls) -> None:
        """remove --yes calls service and shows success."""
        mock_config.return_value = MOCK_CONFIG
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(PlaylistService, "remove_items", return_value=1) as mock_remove:
            result = runner.invoke(
                app, ["library", "playlists", "remove", "12345", "56789", "--yes"]
            )

        assert result.exit_code == 0
        assert "1 item(s)" in result.output
        mock_remove.assert_called_once()
        call_args = mock_remove.call_args
        assert call_args[0][0] == "12345"
        assert call_args[0][1] == ["56789"]
