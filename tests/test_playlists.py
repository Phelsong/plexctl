"""Tests for PlaylistService — regular playlist creation and management."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from plexctl.models import CsvPlaylist, MediaType, Playlist, PlaylistItem, PlaylistType
from plexctl.services.playlists import (
    PlaylistService,
    _parse_m3u_filename,
    _parse_playlist,
    _safe_bool,
    _safe_int,
)

if TYPE_CHECKING:
    from pathlib import Path

# --- Helper function tests -----------------------------------------------------


class TestSafeInt:
    """Tests for _safe_int in playlists module."""

    def test_none_returns_none(self) -> None:
        assert _safe_int(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _safe_int("") is None

    def test_valid_int(self) -> None:
        assert _safe_int(42) == 42

    def test_invalid_string_returns_none(self) -> None:
        assert _safe_int("not_a_number") is None

    def test_float_truncates(self) -> None:
        assert _safe_int(3.7) == 3

    def test_string_int(self) -> None:
        assert _safe_int("10") == 10


class TestSafeBool:
    """Tests for _safe_bool in playlists module."""

    def test_true_bool(self) -> None:
        assert _safe_bool(True) is True

    def test_false_bool(self) -> None:
        assert _safe_bool(False) is False

    def test_int_one(self) -> None:
        assert _safe_bool(1) is True

    def test_int_zero(self) -> None:
        assert _safe_bool(0) is False

    def test_string_true(self) -> None:
        assert _safe_bool("true") is True

    def test_string_one(self) -> None:
        assert _safe_bool("1") is True

    def test_string_false(self) -> None:
        assert _safe_bool("false") is False

    def test_none_returns_false(self) -> None:
        assert _safe_bool(None) is False

    def test_string_yes(self) -> None:
        assert _safe_bool("yes") is True


class TestParsePlaylist:
    """Tests for _parse_playlist."""

    def test_basic_playlist(self) -> None:
        item = {
            "ratingKey": "12345",
            "title": "My Playlist",
            "playlistType": "video",
            "smart": 0,
            "leafCount": 10,
            "composite": "/playlist/thumb",
            "addedAt": "1234567890",
            "updatedAt": "1234567890",
        }
        result = _parse_playlist(item)
        assert result.key == "12345"
        assert result.title == "My Playlist"
        assert result.playlist_type == PlaylistType.VIDEO
        assert result.smart is False
        assert result.item_count == 10

    def test_playlist_type_parsing(self) -> None:
        item = {"ratingKey": "100", "title": "Audio Mix", "playlistType": "audio", "smart": 0}
        result = _parse_playlist(item)
        assert result.playlist_type == PlaylistType.AUDIO

    def test_invalid_playlist_type(self) -> None:
        item = {
            "ratingKey": "200",
            "title": "Unknown",
            "playlistType": "invalid_type",
            "smart": 0,
        }
        result = _parse_playlist(item)
        assert result.playlist_type is None

    def test_missing_fields_use_defaults(self) -> None:
        item = {"ratingKey": "300"}
        result = _parse_playlist(item)
        assert result.key == "300"
        assert result.title == ""
        assert result.playlist_type is None
        assert result.smart is False
        assert result.item_count == 0
        assert result.composite is None
        assert result.added_at is None
        assert result.updated_at is None

    def test_smart_one_is_smart(self) -> None:
        item = {"ratingKey": "400", "title": "Smart One", "smart": 1, "leafCount": 5}
        result = _parse_playlist(item)
        assert result.smart is True

    def test_key_fallback(self) -> None:
        item = {"key": "999"}
        result = _parse_playlist(item)
        assert result.key == "999"


# --- Service method tests ------------------------------------------------------


class TestCreatePlaylist:
    """Test PlaylistService.create_playlist."""

    def test_create_empty_playlist(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "My Playlist",
                    "playlistType": "video",
                    "smart": 0,
                    "leafCount": 0,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.create_playlist(title="My Playlist")

        assert result.title == "My Playlist"
        assert result.key == "500"
        assert result.smart is False
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/playlists"
        params = call_args[1].get("params", {})
        assert params["title"] == "My Playlist"
        assert params["smart"] == "0"

    def test_create_with_items(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        # POST /playlists — returns created playlist
        mock_http.post.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "501",
                    "title": "Seeded Playlist",
                    "playlistType": "video",
                    "smart": 0,
                    "leafCount": 0,
                }
            }
        }
        # GET / — returns machineIdentifier for add_items
        mock_http.get.side_effect = [
            {"MediaContainer": {"machineIdentifier": "abc123"}},
            {  # GET /playlists/501 — refresh after add_items
                "MediaContainer": {
                    "Metadata": {
                        "ratingKey": "501",
                        "title": "Seeded Playlist",
                        "playlistType": "video",
                        "smart": 0,
                        "leafCount": 2,
                    }
                }
            },
        ]
        mock_http.put.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.create_playlist(
                title="Seeded Playlist",
                playlist_type=PlaylistType.VIDEO,
                item_keys=["100", "200"],
            )

        assert result.key == "501"
        assert result.title == "Seeded Playlist"
        assert result.item_count == 2
        # PUT should be called for adding items
        mock_http.put.assert_called()

    def test_empty_title_raises(self) -> None:
        mock_client = MagicMock()
        service = PlaylistService(mock_client)
        with pytest.raises(ValueError, match="title is required"):
            service.create_playlist(title="")


class TestGetPlaylist:
    """Test PlaylistService.get_playlist."""

    def test_get_existing_playlist(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "12345",
                    "title": "My Playlist",
                    "playlistType": "video",
                    "smart": 0,
                    "leafCount": 10,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.get_playlist("12345")

        assert result is not None
        assert result.key == "12345"
        assert result.title == "My Playlist"
        assert result.item_count == 10

    def test_get_nonexistent_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.get_playlist("99999")

        assert result is None

    def test_get_playlist_exception_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Network error")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.get_playlist("500")

        assert result is None


class TestListPlaylists:
    """Test PlaylistService.list_playlists."""

    def test_list_returns_regular_only(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "100",
                        "title": "Regular Playlist",
                        "playlistType": "video",
                        "smart": 0,
                        "leafCount": 5,
                    },
                    {
                        "ratingKey": "200",
                        "title": "Smart Playlist",
                        "playlistType": "video",
                        "smart": 1,
                        "leafCount": 42,
                    },
                    {
                        "ratingKey": "300",
                        "title": "Another Regular",
                        "playlistType": "audio",
                        "smart": 0,
                        "leafCount": 3,
                    },
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            playlists = service.list_playlists()

        assert len(playlists) == 2
        assert all(not p.smart for p in playlists)
        assert playlists[0].title == "Regular Playlist"
        assert playlists[1].title == "Another Regular"

    def test_list_empty(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            playlists = service.list_playlists()

        assert playlists == []

    def test_list_with_section_id(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "100",
                        "title": "Section Playlist",
                        "playlistType": "video",
                        "smart": 0,
                        "leafCount": 5,
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            playlists = service.list_playlists(section_id=2)

        assert len(playlists) == 1
        call_args = mock_http.get.call_args
        params = call_args[1].get("params", {})
        assert params.get("sectionID") == "2"


class TestUpdatePlaylist:
    """Test PlaylistService.update_playlist."""

    def test_update_title(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        # PUT returns None (no body expected)
        mock_http.put.return_value = None
        # GET returns updated playlist
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "12345",
                    "title": "New Title",
                    "playlistType": "video",
                    "smart": 0,
                    "leafCount": 10,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.update_playlist("12345", title="New Title")

        assert result is not None
        assert result.title == "New Title"
        mock_http.put.assert_called_once()

    def test_update_returns_updated(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "12345",
                    "title": "Current Name",
                    "playlistType": "video",
                    "smart": 0,
                    "leafCount": 10,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            # No title means just get the current playlist
            result = service.update_playlist("12345")

        assert result is not None
        assert result.title == "Current Name"

    def test_update_failed_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.put.side_effect = Exception("Update failed")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            result = service.update_playlist("12345", title="New Title")

        assert result is None


class TestDeletePlaylist:
    """Test PlaylistService.delete_playlist."""

    def test_delete_calls_http(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            service.delete_playlist("12345")

        call_args = mock_http.delete.call_args
        assert "/playlists/12345" in call_args[0][0]


class TestAddItems:
    """Test PlaylistService.add_items."""

    def test_add_items_success(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"machineIdentifier": "machine123"}}
        mock_http.put.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            count = service.add_items("500", ["100", "200"])

        assert count == 2
        mock_http.put.assert_called_once()
        call_args = mock_http.put.call_args
        assert "/playlists/500/items" in call_args[0][0]

    def test_empty_item_keys_raises(self) -> None:
        mock_client = MagicMock()
        service = PlaylistService(mock_client)
        with pytest.raises(ValueError, match="At least one item key is required"):
            service.add_items("500", [])


class TestRemoveItems:
    """Test PlaylistService.remove_items."""

    def test_remove_items_success(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.delete.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            count = service.remove_items("500", ["100", "200"])

        assert count == 2
        call_args = mock_http.delete.call_args
        assert "/playlists/500/items" in call_args[0][0]

    def test_empty_item_keys_raises(self) -> None:
        mock_client = MagicMock()
        service = PlaylistService(mock_client)
        with pytest.raises(ValueError, match="At least one item key is required"):
            service.remove_items("500", [])


class TestGetPlaylistItems:
    """Test PlaylistService.get_playlist_items."""

    def test_get_items(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "99999",
                        "title": "Some Movie",
                        "type": "movie",
                        "year": 2023,
                        "duration": 7200000,
                        "thumb": "/thumb/path",
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            items = service.get_playlist_items("500")

        assert len(items) == 1
        assert items[0].key == "99999"
        assert items[0].title == "Some Movie"
        assert items[0].media_type == MediaType.MOVIE
        assert items[0].year == 2023

    def test_empty_items(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            items = service.get_playlist_items("500")

        assert items == []

    def test_get_items_with_limit(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = PlaylistService(mock_client)
            service.get_playlist_items("500", limit=10)

        call_args = mock_http.get.call_args
        params = call_args[1].get("params", {})
        assert params["limit"] == "10"


# --- Model tests --------------------------------------------------------------


class TestPlaylistModel:
    """Tests for Playlist model."""

    def test_default_values(self) -> None:
        pl = Playlist(key="100", title="Test")
        assert pl.key == "100"
        assert pl.title == "Test"
        assert pl.playlist_type is None
        assert pl.smart is False
        assert pl.item_count == 0
        assert pl.composite is None
        assert pl.added_at is None
        assert pl.updated_at is None

    def test_full_construction(self) -> None:
        pl = Playlist(
            key="500",
            title="My Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=10,
            composite="/thumb",
            added_at="1234567890",
            updated_at="1234567891",
        )
        assert pl.playlist_type == PlaylistType.VIDEO
        assert pl.item_count == 10
        assert pl.composite == "/thumb"
        assert pl.added_at == "1234567890"


class TestCsvPlaylistModel:
    """Tests for CsvPlaylist model."""

    def test_all_string_fields(self) -> None:
        csv = CsvPlaylist(
            key="500",
            title="My Playlist",
            playlist_type="video",
            smart="False",
            item_count="10",
            composite="/thumb",
            added_at="1234567890",
            updated_at="1234567891",
        )
        assert csv.key == "500"
        assert csv.title == "My Playlist"
        assert csv.playlist_type == "video"
        assert csv.smart == "False"
        assert csv.item_count == "10"


# --- Converter tests ----------------------------------------------------------


class TestPlaylistConverters:
    """Tests for playlist CSV converters."""

    def test_playlist_to_csv(self) -> None:
        from plexctl.converters import playlist_to_csv

        pl = Playlist(
            key="500",
            title="My Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=10,
            composite="/thumb",
            added_at="1234567890",
            updated_at="1234567891",
        )
        csv_row = playlist_to_csv(pl)
        assert csv_row.key == "500"
        assert csv_row.title == "My Playlist"
        assert csv_row.playlist_type == "video"
        assert csv_row.smart == "False"
        assert csv_row.item_count == "10"

    def test_playlist_to_csv_none_fields(self) -> None:
        from plexctl.converters import playlist_to_csv

        pl = Playlist(key="500", title="Minimal")
        csv_row = playlist_to_csv(pl)
        assert csv_row.playlist_type == ""
        assert csv_row.composite == ""
        assert csv_row.added_at == ""

    def test_playlist_item_to_csv(self) -> None:
        from plexctl.converters import playlist_item_to_csv

        item = PlaylistItem(
            key="100", title="Inception", media_type=MediaType.MOVIE, year=2010, duration=1480000
        )
        csv_row = playlist_item_to_csv(item)
        assert csv_row.key == "100"
        assert csv_row.title == "Inception"
        assert csv_row.media_type == "movie"
        assert csv_row.year == "2010"
        assert csv_row.duration == "1480000"


# --- CSV roundtrip tests -------------------------------------------------------


class TestPlaylistCsvRoundtrip:
    """Tests that playlist models survive CSV roundtrip."""

    def test_playlist_roundtrip(self) -> None:
        from plexctl.converters import playlist_to_csv
        from plexctl.csv_utils import from_csv, to_csv

        pl = Playlist(
            key="500",
            title="Test Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=False,
            item_count=10,
        )
        csv_row = playlist_to_csv(pl)
        csv_content = to_csv([csv_row])

        restored = from_csv(CsvPlaylist, csv_content)
        assert len(restored) == 1
        assert restored[0].key == "500"
        assert restored[0].title == "Test Playlist"
        assert restored[0].playlist_type == "video"

    def test_playlist_item_roundtrip(self) -> None:
        from plexctl.converters import playlist_item_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CsvPlaylistItem

        item = PlaylistItem(
            key="100", title="Inception", media_type=MediaType.MOVIE, year=2010, duration=1480000
        )
        csv_row = playlist_item_to_csv(item)
        csv_content = to_csv([csv_row])

        restored = from_csv(CsvPlaylistItem, csv_content)
        assert len(restored) == 1
        assert restored[0].key == "100"
        assert restored[0].title == "Inception"
        assert restored[0].media_type == "movie"


# --- CSV model registry tests --------------------------------------------------


class TestPlaylistCsvModelRegistry:
    """Tests that playlist CSV models are registered for ingest."""

    def test_playlist_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvPlaylist

        cls = get_model_class("playlist")
        assert cls is not None
        assert cls is CsvPlaylist

    def test_playlist_item_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvPlaylistItem

        cls = get_model_class("playlist_item")
        assert cls is not None
        assert cls is CsvPlaylistItem


# --- M3U parsing tests --------------------------------------------------------


class TestParseM3UFilename:
    """Tests for _parse_m3u_filename."""

    def test_standard_format(self) -> None:
        entry = _parse_m3u_filename("01.Rema, Selena Gomez-Calm Down.flac")
        assert entry.track_number == 1
        assert entry.artists == "Rema, Selena Gomez"
        assert entry.title == "Calm Down"

    def test_single_artist(self) -> None:
        entry = _parse_m3u_filename("02.Selena Gomez-My Mind & Me.flac")
        assert entry.track_number == 2
        assert entry.artists == "Selena Gomez"
        assert entry.title == "My Mind  Me"

    def test_no_track_number(self) -> None:
        entry = _parse_m3u_filename("Selena Gomez-Rare.flac")
        assert entry.track_number is None
        assert entry.artists == "Selena Gomez"
        assert entry.title == "Rare"

    def test_no_hyphen(self) -> None:
        entry = _parse_m3u_filename("UnknownTrack.flac")
        assert entry.track_number is None
        assert entry.artists == ""
        assert entry.title == "UnknownTrack"

    def test_double_digit_track(self) -> None:
        entry = _parse_m3u_filename("25.Selena Gomez, The Scene-Love You Like A Love Song.flac")
        assert entry.track_number == 25
        assert entry.artists == "Selena Gomez, The Scene"
        assert entry.title == "Love You Like A Love Song"

    def test_extension_stripped(self) -> None:
        entry = _parse_m3u_filename("01.Artist-Title.mp3")
        assert entry.title == "Title"
        assert ".mp3" not in entry.title

    def test_raw_preserved(self) -> None:
        line = "01.Rema, Selena Gomez-Calm Down.flac"
        entry = _parse_m3u_filename(line)
        assert entry.raw == line

    def test_strips_special_chars(self) -> None:
        entry = _parse_m3u_filename(
            "#DiesisLive_Giolì & Assia - #DiesisLive [Episode 01 @Milazzo, Sicily].mp3"
        )
        assert entry.artists == "DiesisLiveGiolì  Assia"
        assert entry.title == "DiesisLive Episode 01 Milazzo, Sicily"


class TestParseM3U:
    """Tests for PlaylistService.parse_m3u."""

    def test_simple_file(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text(
            "01.Artist A-Song One.flac\n"
            "02.Artist B-Song Two.flac\n"
            "03.Artist C-Song Three.flac\n",
            encoding="utf-8",
        )
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 3
        assert entries[0].track_number == 1
        assert entries[0].title == "Song One"
        assert entries[2].track_number == 3

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("\n01.Artist-Song.flac\n\n", encoding="utf-8")
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 1

    def test_skips_comments(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("# This is a comment\n01.Artist-Song.flac\n# Another\n", encoding="utf-8")
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 1
        assert entries[0].title == "Song"

    def test_extm3u_header_skipped(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("#EXTM3U\n01.Artist-Song.flac\n", encoding="utf-8")
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 1

    def test_extinf_provides_title(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text(
            "#EXTINF:180,Selena Gomez - Lose You To Love Me\n" "/music/selena/03.flac\n",
            encoding="utf-8",
        )
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 1
        assert entries[0].title == "Lose You To Love Me"

    def test_empty_file(self, tmp_path: Path) -> None:
        m3u = tmp_path / "empty.m3u"
        m3u.write_text("", encoding="utf-8")
        entries = PlaylistService.parse_m3u(str(m3u))
        assert len(entries) == 0

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            PlaylistService.parse_m3u("/nonexistent/path/file.m3u")


class TestImportM3U:
    """Tests for PlaylistService.import_m3u."""

    def test_empty_file_returns_empty_result(self, tmp_path: Path) -> None:
        m3u = tmp_path / "empty.m3u"
        m3u.write_text("", encoding="utf-8")

        client = MagicMock()
        service = PlaylistService(client)
        result = service.import_m3u(str(m3u), "Empty Playlist")
        assert result.total == 0
        assert result.matched == 0
        assert result.unmatched == 0
        assert result.playlist_key == ""

    def test_no_matches(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("01.Unknown Artist-Unknown Song.flac\n", encoding="utf-8")

        client = MagicMock()
        mock_section = MagicMock()
        mock_section.search.return_value = []
        client.server.library.section.return_value = mock_section

        service = PlaylistService(client)
        result = service.import_m3u(str(m3u), "Test Playlist")
        assert result.total == 1
        assert result.matched == 0
        assert result.unmatched == 1
        assert result.unmatched_entries == ["01.Unknown Artist-Unknown Song.flac"]
        assert result.playlist_key == ""

    def test_successful_import(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("01.Artist A-Song One.flac\n02.Artist B-Song Two.flac\n", encoding="utf-8")

        mock_track1 = MagicMock()
        mock_track1.ratingKey = 101
        mock_track1.grandparentTitle = "Artist A"
        mock_track2 = MagicMock()
        mock_track2.ratingKey = 102
        mock_track2.grandparentTitle = "Artist B"

        client = MagicMock()
        mock_section = MagicMock()
        mock_section.search.side_effect = [[mock_track1], [mock_track2]]
        client.server.library.section.return_value = mock_section

        mock_playlist = MagicMock()
        mock_playlist.ratingKey = 999
        client.server.createPlaylist.return_value = mock_playlist

        service = PlaylistService(client)
        result = service.import_m3u(str(m3u), "My Playlist")
        assert result.total == 2
        assert result.matched == 2
        assert result.unmatched == 0
        assert result.playlist_key == "999"
        client.server.createPlaylist.assert_called_once()

    def test_partial_match(self, tmp_path: Path) -> None:
        m3u = tmp_path / "test.m3u"
        m3u.write_text("01.Artist A-Song One.flac\n02.Artist B-Unknown.flac\n", encoding="utf-8")

        mock_track = MagicMock()
        mock_track.ratingKey = 101
        mock_track.grandparentTitle = "Artist A"

        client = MagicMock()
        mock_section = MagicMock()
        mock_section.search.side_effect = [[mock_track], []]
        client.server.library.section.return_value = mock_section

        mock_playlist = MagicMock()
        mock_playlist.ratingKey = 888
        client.server.createPlaylist.return_value = mock_playlist

        service = PlaylistService(client)
        result = service.import_m3u(str(m3u), "Partial")
        assert result.total == 2
        assert result.matched == 1
        assert result.unmatched == 1
        assert result.unmatched_entries == ["02.Artist B-Unknown.flac"]
        assert result.playlist_key == "888"


# --- generate_m3u tests -------------------------------------------------------


class TestGenerateM3U:
    """Tests for PlaylistService.generate_m3u."""

    def test_generates_m3u_from_audio_files(self, tmp_path: Path) -> None:
        """Audio files in a directory are written to an M3U file."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        (music_dir / "01.Artist A-Song One.flac").write_bytes(b"")
        (music_dir / "02.Artist B-Song Two.mp3").write_bytes(b"")

        out = tmp_path / "output.m3u"
        count = PlaylistService.generate_m3u(str(music_dir), str(out))

        assert count == 2
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "#EXTM3U"
        assert "01.Artist A-Song One.flac" in lines
        assert "02.Artist B-Song Two.mp3" in lines

    def test_skips_non_audio_files(self, tmp_path: Path) -> None:
        """Non-audio files (txt, jpg, etc.) are excluded."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        (music_dir / "01.Track.mp3").write_bytes(b"")
        (music_dir / "cover.jpg").write_bytes(b"")
        (music_dir / "notes.txt").write_bytes(b"")
        (music_dir / "readme.md").write_bytes(b"")

        out = tmp_path / "output.m3u"
        count = PlaylistService.generate_m3u(str(music_dir), str(out))

        assert count == 1
        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines == ["#EXTM3U", "01.Track.mp3"]

    def test_sorts_naturally(self, tmp_path: Path) -> None:
        """Files are sorted by natural order (01 before 10)."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        # Create out of order so filesystem order differs from sorted order
        (music_dir / "10.Tenth Track.mp3").write_bytes(b"")
        (music_dir / "02.Second Track.mp3").write_bytes(b"")
        (music_dir / "01.First Track.mp3").write_bytes(b"")

        out = tmp_path / "output.m3u"
        PlaylistService.generate_m3u(str(music_dir), str(out), sort=True)

        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[1] == "01.First Track.mp3"
        assert lines[2] == "02.Second Track.mp3"
        assert lines[3] == "10.Tenth Track.mp3"

    def test_no_sort_keeps_filesystem_order(self, tmp_path: Path) -> None:
        """With sort=False, files are not reordered."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        (music_dir / "01.First.mp3").write_bytes(b"")
        (music_dir / "10.Tenth.mp3").write_bytes(b"")
        (music_dir / "02.Second.mp3").write_bytes(b"")

        out = tmp_path / "output.m3u"
        PlaylistService.generate_m3u(str(music_dir), str(out), sort=False)

        lines = out.read_text(encoding="utf-8").splitlines()
        # All 3 files present, order is filesystem order (not guaranteed but
        # all entries must be there)
        assert len(lines) == 4  # header + 3 files
        assert lines[0] == "#EXTM3U"

    def test_empty_directory(self, tmp_path: Path) -> None:
        """An empty directory produces an M3U with just the header."""
        music_dir = tmp_path / "empty"
        music_dir.mkdir()

        out = tmp_path / "output.m3u"
        count = PlaylistService.generate_m3u(str(music_dir), str(out))

        assert count == 0
        content = out.read_text(encoding="utf-8")
        assert content.strip() == "#EXTM3U"

    def test_supports_all_audio_extensions(self, tmp_path: Path) -> None:
        """All supported audio extensions are included."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        for ext in [".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma"]:
            (music_dir / f"track{ext}").write_bytes(b"")

        out = tmp_path / "output.m3u"
        count = PlaylistService.generate_m3u(str(music_dir), str(out))

        assert count == 8

    def test_case_insensitive_extensions(self, tmp_path: Path) -> None:
        """Uppercase extensions (e.g. .MP3, .FLAC) are recognized."""
        music_dir = tmp_path / "album"
        music_dir.mkdir()
        (music_dir / "track1.MP3").write_bytes(b"")
        (music_dir / "track2.FLAC").write_bytes(b"")

        out = tmp_path / "output.m3u"
        count = PlaylistService.generate_m3u(str(music_dir), str(out))

        assert count == 2

    def test_directory_not_found_raises(self, tmp_path: Path) -> None:
        """A nonexistent directory raises FileNotFoundError."""
        out = tmp_path / "output.m3u"
        with pytest.raises(FileNotFoundError):
            PlaylistService.generate_m3u(str(tmp_path / "nonexistent"), str(out))
