"""Tests for TreeService — hierarchical media tree navigation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plexctl.models import MediaType
from plexctl.services.tree import TreeService, _parse_tree_item, _safe_int

# --- Helpers -------------------------------------------------------------------


def _section_response(items):
    """Build a section tree API response."""
    return {"MediaContainer": {"Metadata": items}}


def _show_response(show_key, show_title, show_type="show", year=2024):
    """Build a show metadata API response."""
    return {
        "MediaContainer": {
            "Metadata": {
                "ratingKey": show_key,
                "title": show_title,
                "type": show_type,
                "year": year,
                "leafCount": 24,
                "viewedLeafCount": 12,
            }
        }
    }


def _children_response(children):
    """Build a children (seasons/episodes) API response."""
    return {"MediaContainer": {"Metadata": children}}


# --- Section tree tests --------------------------------------------------------


class TestGetSectionTree:
    """Tests for TreeService.get_section_tree."""

    def test_get_section_tree_returns_items(self) -> None:
        """get_section_tree parses section items into MediaTreeItem list."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = _section_response(
            [
                {
                    "ratingKey": "100",
                    "title": "Arifureta",
                    "type": "show",
                    "year": 2019,
                    "leafCount": 24,
                },
                {
                    "ratingKey": "200",
                    "title": "One Piece",
                    "type": "show",
                    "year": 1999,
                    "leafCount": 1000,
                },
            ]
        )

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            items = service.get_section_tree(section_key=2)

        assert len(items) == 2
        assert items[0].key == "100"
        assert items[0].title == "Arifureta"
        assert items[0].media_type == MediaType.SHOW
        assert items[0].year == 2019
        assert items[0].leaf_count == 24

        assert items[1].key == "200"
        assert items[1].title == "One Piece"
        assert items[1].year == 1999

    def test_get_section_tree_with_type_filter(self) -> None:
        """get_section_tree passes type filter param when specified."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = _section_response([])

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            service.get_section_tree(section_key=2, media_type="show")

        # Verify the GET was called with type=2 (show maps to "2")
        call_args = mock_http.get.call_args
        assert call_args is not None
        path = call_args[0][0]
        params = call_args[1].get("params", {})
        assert path == "/library/sections/2/all"
        assert params.get("type") == "2"

    def test_get_section_tree_with_movie_type_filter(self) -> None:
        """get_section_tree maps movie media_type to type=1."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = _section_response([])

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            service.get_section_tree(section_key=3, media_type="movie")

        # Verify the GET was called with type=1 (movie maps to "1")
        call_args = mock_http.get.call_args
        assert call_args is not None
        path = call_args[0][0]
        params = call_args[1].get("params", {})
        assert path == "/library/sections/3/all"
        assert params.get("type") == "1"

    def test_get_section_tree_empty_response(self) -> None:
        """get_section_tree returns empty list when no items."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            items = service.get_section_tree(section_key=1)
        assert items == []

    def test_get_section_tree_none_response(self) -> None:
        """get_section_tree returns empty list when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            items = service.get_section_tree(section_key=1)
        assert items == []

    def test_get_section_tree_single_dict(self) -> None:
        """get_section_tree handles single dict instead of list."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {"ratingKey": "100", "title": "Single Show", "type": "show"}
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            items = service.get_section_tree(section_key=1)
        assert len(items) == 1
        assert items[0].title == "Single Show"

    def test_get_section_tree_movie_type(self) -> None:
        """get_section_tree maps movie type correctly."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = _section_response(
            [{"ratingKey": "300", "title": "Inception", "type": "movie", "year": 2010}]
        )

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            items = service.get_section_tree(section_key=3)
        assert len(items) == 1
        assert items[0].media_type == MediaType.MOVIE


# --- Show tree tests -----------------------------------------------------------


class TestGetShowTree:
    """Tests for TreeService.get_show_tree."""

    def test_get_show_tree_with_seasons(self) -> None:
        """get_show_tree returns show with seasons as children."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        show_data = _show_response("100", "Arifureta")
        seasons_data = _children_response(
            [
                {"ratingKey": "110", "title": "Season 1", "type": "season", "leafCount": 12},
                {"ratingKey": "120", "title": "Season 2", "type": "season", "leafCount": 12},
            ]
        )

        mock_http.get.side_effect = [show_data, seasons_data]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_show_tree("100")

        assert result is not None
        assert result.key == "100"
        assert result.title == "Arifureta"
        assert result.media_type == MediaType.SHOW
        assert len(result.children) == 2
        assert result.children[0].title == "Season 1"
        assert result.children[0].parent_key == "100"
        assert result.children[1].title == "Season 2"

    def test_get_show_tree_not_found(self) -> None:
        """get_show_tree returns None when show not found."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_show_tree("999")
        assert result is None

    def test_get_show_tree_none_metadata(self) -> None:
        """get_show_tree returns None when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_show_tree("100")
        assert result is None

    def test_get_show_tree_no_children(self) -> None:
        """get_show_tree returns show with empty children when no seasons."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        show_data = _show_response("100", "Test Show")
        children_data = {"MediaContainer": {"Metadata": []}}

        mock_http.get.side_effect = [show_data, children_data]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_show_tree("100")
        assert result is not None
        assert result.key == "100"
        assert result.children == []

    def test_get_show_tree_children_failure(self) -> None:
        """get_show_tree returns show without children when children fetch fails."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        show_data = _show_response("100", "Test Show")
        mock_http.get.side_effect = [show_data, Exception("Connection error")]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_show_tree("100")
        assert result is not None
        assert result.title == "Test Show"
        assert result.children == []


# --- Season tree tests ---------------------------------------------------------


class TestGetSeasonTree:
    """Tests for TreeService.get_season_tree."""

    def test_get_season_tree_with_episodes(self) -> None:
        """get_season_tree returns season with episodes as children."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        season_data = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "110",
                    "title": "Season 1",
                    "type": "season",
                    "leafCount": 12,
                    "parentTitle": "Arifureta",
                    "parentRatingKey": "100",
                }
            }
        }
        episodes_data = _children_response(
            [
                {
                    "ratingKey": "111",
                    "title": "Episode 1",
                    "type": "episode",
                    "parentTitle": "Season 1",
                    "parentRatingKey": "110",
                },
                {
                    "ratingKey": "112",
                    "title": "Episode 2",
                    "type": "episode",
                    "parentTitle": "Season 1",
                    "parentRatingKey": "110",
                },
            ]
        )

        mock_http.get.side_effect = [season_data, episodes_data]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_season_tree("110")

        assert result is not None
        assert result.key == "110"
        assert result.title == "Season 1"
        assert result.media_type == MediaType.SEASON
        assert result.parent_title == "Arifureta"
        assert len(result.children) == 2
        assert result.children[0].title == "Episode 1"
        assert result.children[0].media_type == MediaType.EPISODE
        assert result.children[0].parent_key == "110"
        assert result.children[1].title == "Episode 2"

    def test_get_season_tree_not_found(self) -> None:
        """get_season_tree returns None when season not found."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_season_tree("999")
        assert result is None

    def test_get_season_tree_none_response(self) -> None:
        """get_season_tree returns None when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_season_tree("110")
        assert result is None

    def test_get_season_tree_no_episodes(self) -> None:
        """get_season_tree returns season with empty children when no episodes."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        season_data = {
            "MediaContainer": {
                "Metadata": {"ratingKey": "110", "title": "Season 1", "type": "season"}
            }
        }
        episodes_data = {"MediaContainer": {"Metadata": []}}

        mock_http.get.side_effect = [season_data, episodes_data]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)
            result = service.get_season_tree("110")
        assert result is not None
        assert result.key == "110"
        assert result.children == []


# --- Helper function tests -----------------------------------------------------


class TestParseTreeItem:
    """Tests for _parse_tree_item helper."""

    def test_parse_tree_item_complete(self) -> None:
        """_parse_tree_item parses full entry."""
        entry = {
            "ratingKey": "100",
            "title": "Test Show",
            "type": "show",
            "year": 2024,
            "leafCount": 24,
            "viewedLeafCount": 12,
        }
        item = _parse_tree_item(entry)
        assert item.key == "100"
        assert item.title == "Test Show"
        assert item.media_type == MediaType.SHOW
        assert item.year == 2024
        assert item.leaf_count == 24
        assert item.viewed_leaf_count == 12

    def test_parse_tree_item_minimal(self) -> None:
        """_parse_tree_item handles minimal entry with key fallback."""
        entry = {"key": "50", "title": "Minimal"}
        item = _parse_tree_item(entry)
        assert item.key == "50"
        assert item.title == "Minimal"
        assert item.media_type is None
        assert item.year is None

    def test_parse_tree_item_with_parent(self) -> None:
        """_parse_tree_item attaches parent key and title."""
        entry = {"ratingKey": "110", "title": "Season 1", "type": "season"}
        item = _parse_tree_item(entry, parent_key="100", parent_title="Test Show")
        assert item.parent_key == "100"
        assert item.parent_title == "Test Show"

    def test_parse_tree_item_unknown_type(self) -> None:
        """_parse_tree_item returns None media_type for unknown types."""
        entry = {"ratingKey": "1", "title": "Book", "type": "book"}
        item = _parse_tree_item(entry)
        assert item.media_type is None

    def test_parse_tree_item_empty_dict(self) -> None:
        """_parse_tree_item handles empty dict with defaults."""
        entry = {}
        item = _parse_tree_item(entry)
        assert item.key == ""
        assert item.title is None


class TestSafeIntTree:
    """Tests for _safe_int in tree module."""

    def test_safe_int_with_int(self) -> None:
        assert _safe_int(42) == 42

    def test_safe_int_with_string(self) -> None:
        assert _safe_int("100") == 100

    def test_safe_int_with_none(self) -> None:
        assert _safe_int(None) is None

    def test_safe_int_with_empty_string(self) -> None:
        assert _safe_int("") is None

    def test_safe_int_with_invalid(self) -> None:
        assert _safe_int("not_a_number") is None


# --- resolve_section_key tests -------------------------------------------------


class TestResolveSectionKey:
    """Tests for TreeService.resolve_section_key."""

    def _make_sections(self, raw_sections):
        """Build LibrarySection list from raw dicts."""
        from plexctl.models import LibrarySection, MediaType

        sections = []
        for s in raw_sections:
            media_type = MediaType.from_plex_type(s.get("type", ""))
            sections.append(
                LibrarySection(
                    key=str(s.get("key", "")),
                    title=s.get("title", ""),
                    section_type=media_type,
                    agent=s.get("agent"),
                    scanner=s.get("scanner"),
                    language=s.get("language"),
                    count=s.get("count", 0),
                )
            )
        return sections

    def test_resolve_numeric_key_directly(self) -> None:
        """resolve_section_key returns numeric keys as-is."""
        mock_client = MagicMock()
        service = TreeService(mock_client)
        result = service.resolve_section_key("2")
        assert result == "2"

    def test_resolve_numeric_key_with_leading_zeros(self) -> None:
        """resolve_section_key handles numeric keys."""
        mock_client = MagicMock()
        service = TreeService(mock_client)
        result = service.resolve_section_key("10")
        assert result == "10"

    def test_resolve_by_exact_title(self) -> None:
        """resolve_section_key finds section by exact title match."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections(
            [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "TV Shows", "type": "show"},
            ]
        )
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("TV Shows")

        assert result == "2"

    def test_resolve_by_case_insensitive_title(self) -> None:
        """resolve_section_key finds section with case-insensitive match."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections([{"key": "2", "title": "TV Shows", "type": "show"}])
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("tv shows")

        assert result == "2"

    def test_resolve_by_partial_title(self) -> None:
        """resolve_section_key finds section by partial title match."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections([{"key": "2", "title": "TV Shows", "type": "show"}])
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("Shows")

        assert result == "2"

    def test_resolve_by_type_alias_shows(self) -> None:
        """resolve_section_key resolves 'shows' to show section by type."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections(
            [
                {"key": "1", "title": "Movies", "type": "movie"},
                {"key": "2", "title": "Anime", "type": "show"},
            ]
        )
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("shows")

        assert result == "2"

    def test_resolve_by_type_alias_movies(self) -> None:
        """resolve_section_key resolves 'movies' to movie section by type."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections(
            [
                {"key": "1", "title": "Films", "type": "movie"},
                {"key": "2", "title": "Anime", "type": "show"},
            ]
        )
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("movies")

        assert result == "1"

    def test_resolve_type_alias_ambiguous_returns_none(self) -> None:
        """resolve_section_key returns None on ambiguous type alias."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        # Two show sections — ambiguous
        sections = self._make_sections(
            [
                {"key": "2", "title": "Anime", "type": "show"},
                {"key": "3", "title": "Western TV", "type": "show"},
            ]
        )
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("shows")

        assert result is None

    def test_resolve_not_found_returns_none(self) -> None:
        """resolve_section_key returns None when no section matches."""
        mock_client = MagicMock()
        mock_library = MagicMock()

        sections = self._make_sections([{"key": "1", "title": "Movies", "type": "movie"}])
        mock_library.list_sections.return_value = sections

        with patch("plexctl.services.library.LibraryService", return_value=mock_library):
            service = TreeService(mock_client)
            result = service.resolve_section_key("nonexistent")

        assert result is None


# --- Integration-style workflow tests ------------------------------------------


class TestTreeWorkflow:
    """Integration-style tests for tree navigation workflows."""

    def test_section_to_show_to_season_navigation(self) -> None:
        """Simulate navigating: section tree → show tree → season tree."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        section_data = _section_response(
            [
                {
                    "ratingKey": "100",
                    "title": "Arifureta",
                    "type": "show",
                    "year": 2019,
                    "leafCount": 24,
                }
            ]
        )

        show_data = _show_response("100", "Arifureta")
        seasons_data = _children_response(
            [{"ratingKey": "110", "title": "Season 1", "type": "season", "leafCount": 12}]
        )

        season_data = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "110",
                    "title": "Season 1",
                    "type": "season",
                    "parentTitle": "Arifureta",
                    "parentRatingKey": "100",
                }
            }
        }
        episodes_data = _children_response(
            [{"ratingKey": "111", "title": "Episode 1", "type": "episode"}]
        )

        mock_http.get.side_effect = [
            section_data,
            show_data,
            seasons_data,
            season_data,
            episodes_data,
        ]

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = TreeService(mock_client)

            # Navigate section → show → season
            items = service.get_section_tree(section_key=2)
            assert len(items) == 1
            assert items[0].title == "Arifureta"

            show = service.get_show_tree("100")
            assert show is not None
            assert show.title == "Arifureta"
            assert len(show.children) == 1
            assert show.children[0].title == "Season 1"

            season = service.get_season_tree("110")
            assert season is not None
            assert season.title == "Season 1"
            assert len(season.children) == 1
            assert season.children[0].title == "Episode 1"
