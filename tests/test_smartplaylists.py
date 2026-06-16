"""Tests for SmartPlaylistService — smart playlist creation and management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from plexctl.models import (
    MediaType,
    PlaylistItem,
    PlaylistType,
    SmartPlaylist,
    SmartPlaylistFilter,
)
from plexctl.services.playlists import (
    SmartPlaylistService,
    _build_plex_filter_query,
    _parse_filters_from_url,
    _parse_playlist_item,
    _parse_smart_playlist,
    _safe_bool,
    _safe_int,
    _safe_str,
)

# --- Helper function tests -----------------------------------------------------


class TestSafeInt:
    """Tests for _safe_int in playlists module."""

    def test_safe_int_with_int(self) -> None:
        assert _safe_int(42) == 42

    def test_safe_int_with_string(self) -> None:
        assert _safe_int("2024") == 2024

    def test_safe_int_with_none(self) -> None:
        assert _safe_int(None) is None

    def test_safe_int_with_empty_string(self) -> None:
        assert _safe_int("") is None

    def test_safe_int_with_invalid(self) -> None:
        assert _safe_int("not_a_number") is None


class TestSafeBool:
    """Tests for _safe_bool in playlists module."""

    def test_safe_bool_true_int(self) -> None:
        assert _safe_bool(1) is True

    def test_safe_bool_false_int(self) -> None:
        assert _safe_bool(0) is False

    def test_safe_bool_true_string(self) -> None:
        assert _safe_bool("true") is True

    def test_safe_bool_one_string(self) -> None:
        assert _safe_bool("1") is True

    def test_safe_bool_false_string(self) -> None:
        assert _safe_bool("false") is False

    def test_safe_bool_none(self) -> None:
        assert _safe_bool(None) is False


class TestSafeStr:
    """Tests for _safe_str in playlists module."""

    def test_safe_str_with_string(self) -> None:
        assert _safe_str("hello") == "hello"

    def test_safe_str_with_int(self) -> None:
        assert _safe_str(42) == "42"

    def test_safe_str_with_none(self) -> None:
        assert _safe_str(None) is None

    def test_safe_str_with_empty(self) -> None:
        assert _safe_str("") is None


# --- Filter query builder tests ------------------------------------------------


class TestBuildPlexFilterQuery:
    """Tests for _build_plex_filter_query."""

    def test_basic_equality_filter(self) -> None:
        filters = [SmartPlaylistFilter(field="genre", operator="=", value="Sci-Fi")]
        params = _build_plex_filter_query(
            filters=filters, name="Test Playlist", playlist_type="video"
        )
        assert params["title"] == "Test Playlist"
        assert params["type"] == "1"
        assert params["genre"] == "Sci-Fi"

    def test_advanced_operator_filter(self) -> None:
        filters = [SmartPlaylistFilter(field="year", operator=">=", value="2019")]
        params = _build_plex_filter_query(filters=filters, name="Recent", playlist_type="video")
        assert params["year"] == "[year>=2019]"

    def test_multiple_filters(self) -> None:
        filters = [
            SmartPlaylistFilter(field="year", operator=">=", value="2019"),
            SmartPlaylistFilter(field="genre", operator="=", value="Sci-Fi"),
        ]
        params = _build_plex_filter_query(
            filters=filters, name="Recent Sci-Fi", playlist_type="video"
        )
        assert params["year"] == "[year>=2019]"
        assert params["genre"] == "Sci-Fi"

    def test_section_id(self) -> None:
        filters = [SmartPlaylistFilter(field="genre", operator="=", value="Action")]
        params = _build_plex_filter_query(
            filters=filters, name="Action", playlist_type="video", section_id="2"
        )
        assert params["sectionID"] == "2"

    def test_sort_parameter(self) -> None:
        filters = [SmartPlaylistFilter(field="genre", operator="=", value="Drama")]
        params = _build_plex_filter_query(
            filters=filters, name="Drama", playlist_type="video", sort="year:desc"
        )
        assert params["sort"] == "year:desc"

    def test_empty_filters_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one filter"):
            _build_plex_filter_query(filters=[], name="Empty", playlist_type="video")

    def test_playlist_type_audio(self) -> None:
        filters = [SmartPlaylistFilter(field="genre", operator="=", value="Rock")]
        params = _build_plex_filter_query(filters=filters, name="Rock", playlist_type="audio")
        assert params["type"] == "2"

    def test_playlist_type_photo(self) -> None:
        filters = [SmartPlaylistFilter(field="genre", operator="=", value="Nature")]
        params = _build_plex_filter_query(filters=filters, name="Nature", playlist_type="photo")
        assert params["type"] == "3"

    def test_contains_operator(self) -> None:
        filters = [SmartPlaylistFilter(field="title", operator="contains", value="Star")]
        params = _build_plex_filter_query(filters=filters, name="Star", playlist_type="video")
        assert params["title"] == "[titlecontainsStar]"


class TestParseFiltersFromUrl:
    """Tests for _parse_filters_from_url."""

    def test_simple_equality_filter(self) -> None:
        url = "/library/playlists/query?genre=Sci-Fi&type=1&title=Test"
        filters = _parse_filters_from_url(url)
        genres = [f for f in filters if f.field == "genre"]
        assert len(genres) == 1
        assert genres[0].value == "Sci-Fi"
        assert genres[0].operator == "="

    def test_advanced_filter_brackets(self) -> None:
        url_decoded = "/library/playlists/query?year=[year>=2019]&type=1"
        filters = _parse_filters_from_url(url_decoded)
        years = [f for f in filters if f.field == "year"]
        assert len(years) == 1
        assert years[0].operator == ">="
        assert years[0].value == "2019"

    def test_empty_url(self) -> None:
        assert _parse_filters_from_url("") == []
        assert _parse_filters_from_url(None) == []  # type: ignore[arg-type]

    def test_url_without_query(self) -> None:
        url = "/library/playlists/query"
        filters = _parse_filters_from_url(url)
        assert filters == []

    def test_structural_keys_excluded(self) -> None:
        url = (
            "/library/playlists/query?"
            "type=1&title=Test&limit=100"
            "&sort=year:desc&genre=Action"
        )
        filters = _parse_filters_from_url(url)
        fields = [f.field for f in filters]
        assert "type" not in fields
        assert "title" not in fields
        assert "limit" not in fields
        assert "sort" not in fields
        assert "genre" in fields


# --- Parse playlist item tests -------------------------------------------------


class TestParsePlaylistItem:
    """Tests for _parse_playlist_item."""

    def test_parse_complete_item(self) -> None:
        item = {
            "ratingKey": "100",
            "title": "Inception",
            "type": "movie",
            "year": 2010,
            "duration": 1480000,
            "thumb": "/library/metadata/100/thumb",
        }
        result = _parse_playlist_item(item)
        assert result.key == "100"
        assert result.title == "Inception"
        assert result.media_type == MediaType.MOVIE
        assert result.year == 2010
        assert result.duration == 1480000
        assert result.thumb == "/library/metadata/100/thumb"

    def test_parse_minimal_item(self) -> None:
        item = {"ratingKey": "999"}
        result = _parse_playlist_item(item)
        assert result.key == "999"
        assert result.title == ""
        assert result.media_type is None
        assert result.year is None
        assert result.duration is None

    def test_parse_unknown_type_maps_to_none(self) -> None:
        item = {"ratingKey": "1", "type": "book"}
        result = _parse_playlist_item(item)
        assert result.media_type is None


# --- Parse smart playlist tests ------------------------------------------------


class TestParseSmartPlaylist:
    """Tests for _parse_smart_playlist."""

    def test_parse_complete_playlist(self) -> None:
        item = {
            "ratingKey": "500",
            "title": "Recent Sci-Fi",
            "playlistType": "video",
            "smart": 1,
            "leafCount": 42,
            "composite": "/playlists/500/composite",
            "addedAt": "1700000000",
            "updatedAt": "1700100000",
        }
        result = _parse_smart_playlist(item)
        assert result.key == "500"
        assert result.title == "Recent Sci-Fi"
        assert result.playlist_type == PlaylistType.VIDEO
        assert result.smart is True
        assert result.item_count == 42

    def test_parse_playlist_with_no_type(self) -> None:
        item = {"ratingKey": "501", "title": "Custom Playlist", "smart": True}
        result = _parse_smart_playlist(item)
        assert result.playlist_type is None

    def test_parse_playlist_with_content_url(self) -> None:
        item = {
            "ratingKey": "502",
            "title": "Action",
            "smart": 1,
            "content": "/library/playlists/query?genre=Action&type=1",
        }
        result = _parse_smart_playlist(item)
        assert result.key == "502"
        # The filter from the content URL should be parsed
        genre_filters = [f for f in result.filters if f.field == "genre"]
        assert len(genre_filters) == 1
        assert genre_filters[0].value == "Action"


# --- SmartPlaylistService tests ------------------------------------------------


class TestCreateSmartPlaylist:
    """Tests for SmartPlaylistService.create_smart_playlist."""

    def test_create_smart_playlist_returns_playlist(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "Recent Sci-Fi",
                    "playlistType": "video",
                    "smart": 1,
                    "leafCount": 0,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            filters = [
                SmartPlaylistFilter(field="year", operator=">=", value="2019"),
                SmartPlaylistFilter(field="genre", operator="=", value="Sci-Fi"),
            ]
            result = service.create_smart_playlist(
                name="Recent Sci-Fi", filters=filters, playlist_type=PlaylistType.VIDEO
            )

        assert result.title == "Recent Sci-Fi"
        assert result.smart is True

    def test_create_smart_playlist_requires_name(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            filters = [SmartPlaylistFilter(field="genre", operator="=", value="Action")]
            with pytest.raises(ValueError, match="name is required"):
                service.create_smart_playlist(name="", filters=filters)

    def test_create_smart_playlist_requires_filters(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            with pytest.raises(ValueError, match="At least one filter"):
                service.create_smart_playlist(name="Empty Playlist", filters=[])

    def test_create_smart_playlist_sends_correct_params(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "Action",
                    "playlistType": "video",
                    "smart": 1,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            filters = [SmartPlaylistFilter(field="genre", operator="=", value="Action")]
            service.create_smart_playlist(
                name="Action", filters=filters, playlist_type=PlaylistType.VIDEO
            )

        call_args = mock_http.post.call_args
        assert call_args[0][0] == "/playlists/query"
        params = call_args[1].get("params", {})
        assert params["genre"] == "Action"
        assert params["type"] == "1"


class TestGetSmartPlaylist:
    """Tests for SmartPlaylistService.get_smart_playlist."""

    def test_get_smart_playlist_returns_playlist(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "Recent Sci-Fi",
                    "playlistType": "video",
                    "smart": 1,
                    "leafCount": 42,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.get_smart_playlist("500")

        assert result is not None
        assert result.key == "500"
        assert result.title == "Recent Sci-Fi"
        assert result.item_count == 42

    def test_get_smart_playlist_not_found(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.get_smart_playlist("9999")

        assert result is None

    def test_get_smart_playlist_exception_returns_none(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Network error")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.get_smart_playlist("500")

        assert result is None


class TestListSmartPlaylists:
    """Tests for SmartPlaylistService.list_smart_playlists."""

    def test_list_smart_playlists_returns_playlists(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "500",
                        "title": "Recent Sci-Fi",
                        "playlistType": "video",
                        "smart": 1,
                        "leafCount": 42,
                    },
                    {
                        "ratingKey": "501",
                        "title": "Action Movies",
                        "playlistType": "video",
                        "smart": 1,
                        "leafCount": 15,
                    },
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            playlists = service.list_smart_playlists()

        assert len(playlists) == 2
        assert playlists[0].title == "Recent Sci-Fi"
        assert playlists[1].title == "Action Movies"

    def test_list_smart_playlists_filters_non_smart(self) -> None:
        """list_smart_playlists filters out non-smart playlists by default."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "500",
                        "title": "Smart Playlist",
                        "playlistType": "video",
                        "smart": 1,
                        "leafCount": 42,
                    },
                    {
                        "ratingKey": "501",
                        "title": "Manual Playlist",
                        "playlistType": "video",
                        "smart": 0,
                        "leafCount": 15,
                    },
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            playlists = service.list_smart_playlists()

        assert len(playlists) == 1
        assert playlists[0].title == "Smart Playlist"

    def test_list_smart_playlists_none_response(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            playlists = service.list_smart_playlists()

        assert playlists == []

    def test_list_smart_playlists_with_section(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "500",
                        "title": "Section Playlist",
                        "playlistType": "video",
                        "smart": 1,
                        "leafCount": 10,
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            playlists = service.list_smart_playlists(section_id="2")

        assert len(playlists) == 1
        call_args = mock_http.get.call_args
        params = call_args[1].get("params", {})
        assert params.get("playlistType") == "smart"
        assert params.get("sectionID") == "2"


class TestDeleteSmartPlaylist:
    """Tests for SmartPlaylistService.delete_smart_playlist."""

    def test_delete_smart_playlist_sends_delete(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            service.delete_smart_playlist("500")

        call_args = mock_http.delete.call_args
        assert "/playlists/500" in call_args[0][0]


class TestGetPlaylistItems:
    """Tests for SmartPlaylistService.get_playlist_items."""

    def test_get_playlist_items_returns_items(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "100",
                        "title": "Inception",
                        "type": "movie",
                        "year": 2010,
                        "duration": 1480000,
                    },
                    {"ratingKey": "101", "title": "Interstellar", "type": "movie", "year": 2014},
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            items = service.get_playlist_items("500")

        assert len(items) == 2
        assert items[0].title == "Inception"
        assert items[0].media_type == MediaType.MOVIE
        assert items[1].title == "Interstellar"

    def test_get_playlist_items_with_limit(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            service.get_playlist_items("500", limit=10)

        call_args = mock_http.get.call_args
        params = call_args[1].get("params", {})
        assert params["limit"] == "10"

    def test_get_playlist_items_none_response(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            items = service.get_playlist_items("500")

        assert items == []


class TestUpdateSmartPlaylist:
    """Tests for SmartPlaylistService.update_smart_playlist."""

    def test_update_smart_playlist_title(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        # First call: get current playlist
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "Old Name",
                    "playlistType": "video",
                    "smart": 1,
                    "leafCount": 10,
                }
            }
        }
        mock_http.put.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.update_smart_playlist("500", name="New Name")

        assert result is not None
        # PUT should be called for the title update
        mock_http.put.assert_called()

    def test_update_smart_playlist_no_changes_returns_current(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "500",
                    "title": "Current Name",
                    "playlistType": "video",
                    "smart": 1,
                    "leafCount": 10,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.update_smart_playlist("500")

        assert result is not None
        assert result.title == "Current Name"

    def test_update_smart_playlist_not_found(self) -> None:
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SmartPlaylistService(mock_client)
            result = service.update_smart_playlist("9999", name="New Name")

        assert result is None


# --- Model tests --------------------------------------------------------------


class TestSmartPlaylistFilterModel:
    """Tests for SmartPlaylistFilter model."""

    def test_filter_with_default_operator(self) -> None:
        filt = SmartPlaylistFilter(field="genre", value="Sci-Fi")
        assert filt.operator == "="

    def test_filter_with_explicit_operator(self) -> None:
        filt = SmartPlaylistFilter(field="year", operator=">=", value="2019")
        assert filt.operator == ">="
        assert filt.field == "year"
        assert filt.value == "2019"


class TestSmartPlaylistModel:
    """Tests for SmartPlaylist model."""

    def test_smart_playlist_minimal(self) -> None:
        pl = SmartPlaylist(key="500", title="Test")
        assert pl.key == "500"
        assert pl.title == "Test"
        assert pl.smart is True
        assert pl.item_count == 0
        assert pl.filters == []

    def test_smart_playlist_full(self) -> None:
        pl = SmartPlaylist(
            key="500",
            title="Recent Sci-Fi",
            playlist_type=PlaylistType.VIDEO,
            smart=True,
            item_count=42,
            composite="/playlists/500/composite",
            added_at="1700000000",
            updated_at="1700100000",
            filters=[
                SmartPlaylistFilter(field="year", operator=">=", value="2019"),
                SmartPlaylistFilter(field="genre", operator="=", value="Sci-Fi"),
            ],
        )
        assert pl.playlist_type == PlaylistType.VIDEO
        assert len(pl.filters) == 2
        assert pl.filters[0].field == "year"


class TestPlaylistItemModel:
    """Tests for PlaylistItem model."""

    def test_playlist_item_minimal(self) -> None:
        item = PlaylistItem(key="100")
        assert item.key == "100"
        assert item.title == ""
        assert item.media_type is None

    def test_playlist_item_full(self) -> None:
        item = PlaylistItem(
            key="100",
            title="Inception",
            media_type=MediaType.MOVIE,
            year=2010,
            duration=1480000,
            thumb="/thumb/100",
        )
        assert item.title == "Inception"
        assert item.media_type == MediaType.MOVIE
        assert item.year == 2010
        assert item.duration == 1480000


class TestPlaylistTypeEnum:
    """Tests for PlaylistType enum."""

    def test_video_type(self) -> None:
        assert PlaylistType.VIDEO.value == "video"

    def test_audio_type(self) -> None:
        assert PlaylistType.AUDIO.value == "audio"

    def test_photo_type(self) -> None:
        assert PlaylistType.PHOTO.value == "photo"


# --- CSV converter tests ------------------------------------------------------


class TestSmartPlaylistConverters:
    """Tests for smart playlist CSV converters."""

    def test_smart_playlist_filter_to_csv(self) -> None:
        from plexctl.converters import smart_playlist_filter_to_csv

        filt = SmartPlaylistFilter(field="year", operator=">=", value="2019")
        csv_row = smart_playlist_filter_to_csv(filt)
        assert csv_row.field == "year"
        assert csv_row.operator == ">="
        assert csv_row.value == "2019"

    def test_smart_playlist_to_csv(self) -> None:
        from plexctl.converters import smart_playlist_to_csv

        pl = SmartPlaylist(
            key="500",
            title="Recent Sci-Fi",
            playlist_type=PlaylistType.VIDEO,
            smart=True,
            item_count=42,
            filters=[
                SmartPlaylistFilter(field="year", operator=">=", value="2019"),
                SmartPlaylistFilter(field="genre", operator="=", value="Sci-Fi"),
            ],
        )
        csv_row = smart_playlist_to_csv(pl)
        assert csv_row.key == "500"
        assert csv_row.title == "Recent Sci-Fi"
        assert csv_row.playlist_type == "video"
        assert csv_row.smart == "True"
        assert csv_row.item_count == "42"
        assert "year>=2019" in csv_row.filters
        assert "genre=Sci-Fi" in csv_row.filters

    def test_smart_playlist_to_csv_no_filters(self) -> None:
        from plexctl.converters import smart_playlist_to_csv

        pl = SmartPlaylist(key="501", title="Empty Filters", filters=[])
        csv_row = smart_playlist_to_csv(pl)
        assert csv_row.filters == ""

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

    def test_playlist_item_to_csv_none_fields(self) -> None:
        from plexctl.converters import playlist_item_to_csv

        item = PlaylistItem(key="100")
        csv_row = playlist_item_to_csv(item)
        assert csv_row.media_type == ""
        assert csv_row.year == ""
        assert csv_row.duration == ""


# --- CSV roundtrip tests -------------------------------------------------------


class TestSmartPlaylistCsvRoundtrip:
    """Tests that smart playlist models survive CSV roundtrip."""

    def test_smart_playlist_filter_roundtrip(self) -> None:
        from plexctl.converters import smart_playlist_filter_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CsvSmartPlaylistFilter

        filt = SmartPlaylistFilter(field="genre", operator="=", value="Action")
        csv_row = smart_playlist_filter_to_csv(filt)
        csv_content = to_csv([csv_row])

        restored = from_csv(CsvSmartPlaylistFilter, csv_content)
        assert len(restored) == 1
        assert restored[0].field == "genre"
        assert restored[0].operator == "="
        assert restored[0].value == "Action"

    def test_smart_playlist_roundtrip(self) -> None:
        from plexctl.converters import smart_playlist_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CsvSmartPlaylist

        pl = SmartPlaylist(
            key="500",
            title="Test Playlist",
            playlist_type=PlaylistType.VIDEO,
            smart=True,
            item_count=10,
            filters=[SmartPlaylistFilter(field="genre", operator="=", value="Drama")],
        )
        csv_row = smart_playlist_to_csv(pl)
        csv_content = to_csv([csv_row])

        restored = from_csv(CsvSmartPlaylist, csv_content)
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


class TestSmartPlaylistCsvModelRegistry:
    """Tests that smart playlist CSV models are registered for ingest."""

    def test_smart_playlist_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvSmartPlaylist

        cls = get_model_class("smart_playlist")
        assert cls is not None
        assert cls is CsvSmartPlaylist

    def test_smart_playlist_filter_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvSmartPlaylistFilter

        cls = get_model_class("smart_playlist_filter")
        assert cls is not None
        assert cls is CsvSmartPlaylistFilter

    def test_playlist_item_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvPlaylistItem

        cls = get_model_class("playlist_item")
        assert cls is not None
        assert cls is CsvPlaylistItem
