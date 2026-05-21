"""Tests for SearchService — advanced metadata search operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from plexctl.models import MediaType, SearchResult, SimilarMedia
from plexctl.services.search import SearchService, _parse_search_result, _safe_float, _safe_int

# --- Helper function tests -----------------------------------------------------


class TestSafeIntSearch:
    """Tests for _safe_int in search module."""

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


class TestSafeFloat:
    """Tests for _safe_float helper."""

    def test_safe_float_with_float(self) -> None:
        assert _safe_float(8.5) == 8.5

    def test_safe_float_with_string(self) -> None:
        assert _safe_float("9.2") == 9.2

    def test_safe_float_with_none(self) -> None:
        assert _safe_float(None) is None

    def test_safe_float_with_empty_string(self) -> None:
        assert _safe_float("") is None

    def test_safe_float_with_invalid(self) -> None:
        assert _safe_float("not_a_float") is None

    def test_safe_float_with_int(self) -> None:
        assert _safe_float(7) == 7.0


# --- Parse search result tests -------------------------------------------------


class TestParseSearchResult:
    """Tests for _parse_search_result helper."""

    def test_parse_complete_item(self) -> None:
        """_parse_search_result handles a full API response."""
        item = {
            "ratingKey": "12345",
            "title": "Inception",
            "type": "movie",
            "year": 2010,
            "summary": "A thief who steals corporate secrets",
            "rating": 8.8,
            "thumb": "/library/metadata/12345/thumb",
            "librarySectionID": "2",
            "librarySectionTitle": "Movies",
        }
        result = _parse_search_result(item)
        assert result.key == "12345"
        assert result.title == "Inception"
        assert result.media_type == MediaType.MOVIE
        assert result.year == 2010
        assert result.summary == "A thief who steals corporate secrets"
        assert result.rating == 8.8
        assert result.thumb == "/library/metadata/12345/thumb"
        assert result.section_key == "2"
        assert result.section_title == "Movies"

    def test_parse_minimal_item(self) -> None:
        """_parse_search_result handles minimal response."""
        item = {"ratingKey": "999"}
        result = _parse_search_result(item)
        assert result.key == "999"
        assert result.title == ""
        assert result.media_type is None
        assert result.year is None
        assert result.summary is None
        assert result.rating is None

    def test_parse_unknown_type(self) -> None:
        """_parse_search_result maps unknown type to None."""
        item = {"ratingKey": "1", "title": "Book", "type": "book"}
        result = _parse_search_result(item)
        assert result.media_type is None

    def test_parse_key_fallback(self) -> None:
        """_parse_search_result falls back to 'key' if ratingKey missing."""
        item = {"key": "50", "title": "Test"}
        result = _parse_search_result(item)
        assert result.key == "50"

    def test_parse_empty_section_key(self) -> None:
        """_parse_search_result returns None for empty section_key."""
        item = {"ratingKey": "1", "librarySectionID": ""}
        result = _parse_search_result(item)
        assert result.section_key is None

    def test_parse_show_type(self) -> None:
        """_parse_search_result maps show type correctly."""
        item = {"ratingKey": "2", "type": "show"}
        result = _parse_search_result(item)
        assert result.media_type == MediaType.SHOW

    def test_parse_summary_strips_empty(self) -> None:
        """_parse_search_result returns None for empty summary."""
        item = {"ratingKey": "1", "summary": ""}
        result = _parse_search_result(item)
        assert result.summary is None


# --- Search by key tests -------------------------------------------------------


class TestSearchByKey:
    """Tests for SearchService.search_by_key."""

    def test_search_by_key_returns_result(self) -> None:
        """search_by_key returns a SearchResult for a valid key."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "12345",
                    "title": "Inception",
                    "type": "movie",
                    "year": 2010,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            result = service.search_by_key("12345")

        assert result is not None
        assert result.key == "12345"
        assert result.title == "Inception"
        assert result.media_type == MediaType.MOVIE
        assert result.year == 2010

    def test_search_by_key_not_found(self) -> None:
        """search_by_key returns None when item doesn't exist."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            result = service.search_by_key("99999")

        assert result is None

    def test_search_by_key_none_response(self) -> None:
        """search_by_key returns None when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            result = service.search_by_key("12345")

        assert result is None

    def test_search_by_key_list_response(self) -> None:
        """search_by_key handles list response (takes first item)."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [{"ratingKey": "1", "title": "First", "type": "movie"}]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            result = service.search_by_key("1")

        assert result is not None
        assert result.title == "First"

    def test_search_by_key_empty_metadata(self) -> None:
        """search_by_key returns None for empty metadata."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": {}}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            result = service.search_by_key("1")

        assert result is None


# --- Advanced search tests -----------------------------------------------------


class TestSearchAdvanced:
    """Tests for SearchService.search_advanced."""

    def test_search_advanced_returns_results(self) -> None:
        """search_advanced returns results from Hub search."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Hub": [
                    {
                        "Metadata": [
                            {
                                "ratingKey": "100",
                                "title": "Inception",
                                "type": "movie",
                                "year": 2010,
                            },
                            {
                                "ratingKey": "200",
                                "title": "Interstellar",
                                "type": "movie",
                                "year": 2014,
                            },
                        ]
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_advanced("space")

        assert len(results) == 2
        assert results[0].title == "Inception"
        assert results[1].title == "Interstellar"

    def test_search_advanced_empty_query(self) -> None:
        """search_advanced returns empty list for empty query."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_advanced("")

        assert results == []
        mock_http.get.assert_not_called()

    def test_search_advanced_none_response(self) -> None:
        """search_advanced returns empty list for None response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_advanced("test")

        assert results == []

    def test_search_advanced_with_type_filter(self) -> None:
        """search_advanced passes type filter as numeric code."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Hub": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_advanced("action", media_type="movie")

        call_args = mock_http.get.call_args
        assert call_args[0][0] == "/hubs/search"
        params = call_args[1].get("params", {})
        assert params.get("type") == "1"

    def test_search_advanced_with_section(self) -> None:
        """search_advanced passes section filter."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Hub": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_advanced("test", section="2")

        call_args = mock_http.get.call_args
        params = call_args[1].get("params", {})
        assert params.get("sectionId") == "2"

    def test_search_advanced_single_hub_dict(self) -> None:
        """search_advanced handles single Hub dict instead of list."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Hub": {"Metadata": {"ratingKey": "100", "title": "Solo Item", "type": "movie"}}
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_advanced("solo")

        assert len(results) == 1
        assert results[0].title == "Solo Item"


# --- Search by actor tests ----------------------------------------------------


class TestSearchByActor:
    """Tests for SearchService.search_by_actor."""

    def test_search_by_actor_returns_results(self) -> None:
        """search_by_actor passes actor param and returns results."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "1", "title": "The Revenant", "type": "movie", "year": 2015}
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_actor("Leonardo DiCaprio")

        assert len(results) == 1
        assert results[0].title == "The Revenant"
        call_args = mock_http.get.call_args
        assert call_args[0][0] == "/library/all"
        params = call_args[1].get("params", {})
        assert params.get("actor") == "Leonardo DiCaprio"

    def test_search_by_actor_empty_name(self) -> None:
        """search_by_actor returns empty list for empty actor name."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_actor("")

        assert results == []
        mock_http.get.assert_not_called()

    def test_search_by_actor_with_show_type(self) -> None:
        """search_by_actor passes correct type code for shows."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_by_actor("Actor", media_type="show")

        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("type") == "2"


# --- Search by director tests -------------------------------------------------


class TestSearchByDirector:
    """Tests for SearchService.search_by_director."""

    def test_search_by_director_returns_results(self) -> None:
        """search_by_director passes director param and returns results."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "10", "title": "Oppenheimer", "type": "movie", "year": 2023}
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_director("Christopher Nolan")

        assert len(results) == 1
        assert results[0].title == "Oppenheimer"
        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("director") == "Christopher Nolan"

    def test_search_by_director_empty_name(self) -> None:
        """search_by_director returns empty list for empty name."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_director("")

        assert results == []
        mock_http.get.assert_not_called()


# --- Search by title tests ----------------------------------------------------


class TestSearchByTitle:
    """Tests for SearchService.search_by_title."""

    def test_search_by_title_returns_results(self) -> None:
        """search_by_title passes title param and returns results."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "5", "title": "The Matrix", "type": "movie", "year": 1999}
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_title("Matrix")

        assert len(results) == 1
        assert results[0].title == "The Matrix"
        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("title") == "Matrix"

    def test_search_by_title_empty_query(self) -> None:
        """search_by_title returns empty list for empty query."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_title("")

        assert results == []
        mock_http.get.assert_not_called()

    def test_search_by_title_with_section(self) -> None:
        """search_by_title uses section endpoint when section provided."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_by_title("Test", section="2")

        call_args = mock_http.get.call_args
        assert call_args[0][0] == "/library/sections/2/all"


# --- Search by year tests -----------------------------------------------------


class TestSearchByYear:
    """Tests for SearchService.search_by_year."""

    def test_search_by_year_returns_results(self) -> None:
        """search_by_year passes year param and returns results."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "7", "title": "Dune: Part Two", "type": "movie", "year": 2024}
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_year(2024)

        assert len(results) == 1
        assert results[0].year == 2024
        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("year") == "2024"

    def test_search_by_year_with_type(self) -> None:
        """search_by_year passes type filter."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_by_year(2024, media_type="movie")

        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("type") == "1"


# --- Search by genre tests ----------------------------------------------------


class TestSearchByGenre:
    """Tests for SearchService.search_by_genre."""

    def test_search_by_genre_returns_results(self) -> None:
        """search_by_genre passes genre param and returns results."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "8", "title": "Die Hard", "type": "movie", "year": 1988}
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_genre("Action")

        assert len(results) == 1
        assert results[0].title == "Die Hard"
        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("genre") == "Action"

    def test_search_by_genre_empty_genre(self) -> None:
        """search_by_genre returns empty list for empty genre."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_by_genre("")

        assert results == []
        mock_http.get.assert_not_called()


# --- Find similar tests -------------------------------------------------------


class TestFindSimilar:
    """Tests for SearchService.find_similar."""

    def test_find_similar_returns_results(self) -> None:
        """find_similar returns related media items."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": [
                    {
                        "ratingKey": "200",
                        "title": "Tenet",
                        "type": "movie",
                        "year": 2020,
                        "similarity": 92,
                    },
                    {
                        "ratingKey": "201",
                        "title": "Dunkirk",
                        "type": "movie",
                        "year": 2017,
                        "similarity": 85,
                    },
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            similar = service.find_similar("12345")

        assert len(similar) == 2
        assert similar[0].title == "Tenet"
        assert similar[0].similarity == 92
        assert similar[1].title == "Dunkirk"
        assert similar[1].similarity == 85

    def test_find_similar_none_response(self) -> None:
        """find_similar returns empty list for None response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            similar = service.find_similar("12345")

        assert similar == []

    def test_find_similar_empty_metadata(self) -> None:
        """find_similar returns empty list for empty metadata."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            similar = service.find_similar("12345")

        assert similar == []

    def test_find_similar_calls_correct_endpoint(self) -> None:
        """find_similar calls GET /library/metadata/{key}/similar."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.find_similar("42", limit=5)

        call_args = mock_http.get.call_args
        assert "/library/metadata/42/similar" in call_args[0][0]
        params = call_args[1].get("params", {})
        assert params.get("limit") == "5"

    def test_find_similar_single_dict(self) -> None:
        """find_similar handles single dict metadata."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "300",
                    "title": "Memento",
                    "type": "movie",
                    "similarity": 78,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            similar = service.find_similar("12345")

        assert len(similar) == 1
        assert similar[0].title == "Memento"
        assert similar[0].similarity == 78


# --- Search TMDB tests --------------------------------------------------------


class TestSearchTmdb:
    """Tests for SearchService.search_tmdb."""

    def test_search_tmdb_returns_results(self) -> None:
        """search_tmdb passes query and type params."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Hub": [
                    {
                        "Metadata": [
                            {
                                "ratingKey": "50",
                                "title": "The Shawshank Redemption",
                                "type": "movie",
                                "year": 1994,
                                "librarySectionTitle": "Movies",
                            }
                        ]
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_tmdb("Shawshank")

        assert len(results) == 1
        assert results[0].title == "The Shawshank Redemption"
        assert results[0].section_title == "Movies"

    def test_search_tmdb_empty_query(self) -> None:
        """search_tmdb returns empty list for empty query."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            results = service.search_tmdb("")

        assert results == []
        mock_http.get.assert_not_called()

    def test_search_tmdb_with_year(self) -> None:
        """search_tmdb passes year param when provided."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Hub": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = SearchService(mock_client)
            service.search_tmdb("Matrix", year=1999)

        params = mock_http.get.call_args[1].get("params", {})
        assert params.get("year") == "1999"


# --- Model tests ---------------------------------------------------------------


class TestSearchResultModel:
    """Tests for SearchResult model."""

    def test_search_result_minimal(self) -> None:
        result = SearchResult(key="12345")
        assert result.key == "12345"
        assert result.title == ""
        assert result.media_type is None
        assert result.year is None

    def test_search_result_full(self) -> None:
        result = SearchResult(
            key="100",
            title="Inception",
            media_type=MediaType.MOVIE,
            year=2010,
            summary="A thief who steals corporate secrets",
            rating=8.8,
            thumb="/thumb/100",
            section_key="2",
            section_title="Movies",
        )
        assert result.title == "Inception"
        assert result.media_type == MediaType.MOVIE
        assert result.year == 2010
        assert result.rating == 8.8
        assert result.section_key == "2"


class TestSimilarMediaModel:
    """Tests for SimilarMedia model."""

    def test_similar_media_minimal(self) -> None:
        media = SimilarMedia(key="200")
        assert media.key == "200"
        assert media.title == ""
        assert media.similarity is None

    def test_similar_media_full(self) -> None:
        media = SimilarMedia(
            key="200",
            title="Tenet",
            media_type=MediaType.MOVIE,
            year=2020,
            similarity=92,
            thumb="/thumb/200",
        )
        assert media.title == "Tenet"
        assert media.similarity == 92
        assert media.thumb == "/thumb/200"


# --- CSV converter tests ------------------------------------------------------


class TestSearchConverters:
    """Tests for search-related CSV converters."""

    def test_search_result_to_csv(self) -> None:
        from plexctl.converters import search_result_to_csv

        result = SearchResult(
            key="100",
            title="Inception",
            media_type=MediaType.MOVIE,
            year=2010,
            rating=8.8,
            section_key="2",
            section_title="Movies",
        )
        csv_row = search_result_to_csv(result)
        assert csv_row.key == "100"
        assert csv_row.title == "Inception"
        assert csv_row.media_type == "movie"
        assert csv_row.year == "2010"
        assert csv_row.rating == "8.8"
        assert csv_row.section_key == "2"
        assert csv_row.section_title == "Movies"

    def test_search_result_to_csv_none_fields(self) -> None:
        from plexctl.converters import search_result_to_csv

        result = SearchResult(key="100")
        csv_row = search_result_to_csv(result)
        assert csv_row.media_type == ""
        assert csv_row.year == ""
        assert csv_row.rating == ""
        assert csv_row.summary == ""
        assert csv_row.thumb == ""

    def test_similar_media_to_csv(self) -> None:
        from plexctl.converters import similar_media_to_csv

        media = SimilarMedia(
            key="200", title="Tenet", media_type=MediaType.MOVIE, year=2020, similarity=92
        )
        csv_row = similar_media_to_csv(media)
        assert csv_row.key == "200"
        assert csv_row.title == "Tenet"
        assert csv_row.media_type == "movie"
        assert csv_row.year == "2020"
        assert csv_row.similarity == "92"

    def test_similar_media_to_csv_none_similarity(self) -> None:
        from plexctl.converters import similar_media_to_csv

        media = SimilarMedia(key="200", title="Unknown")
        csv_row = similar_media_to_csv(media)
        assert csv_row.similarity == ""
        assert csv_row.year == ""


# --- CSV roundtrip tests -------------------------------------------------------


class TestSearchCsvRoundtrip:
    """Tests that search models survive CSV roundtrip."""

    def test_search_result_roundtrip(self) -> None:
        from plexctl.converters import search_result_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CsvSearchResult

        results = [
            SearchResult(
                key="1",
                title="Test Movie",
                media_type=MediaType.MOVIE,
                year=2024,
                rating=9.0,
                section_key="2",
                section_title="Movies",
            )
        ]
        rows = [search_result_to_csv(r) for r in results]
        csv_content = to_csv(rows)

        restored = from_csv(CsvSearchResult, csv_content)
        assert len(restored) == 1
        assert restored[0].key == "1"
        assert restored[0].title == "Test Movie"
        assert restored[0].media_type == "movie"
        assert restored[0].year == "2024"

    def test_similar_media_roundtrip(self) -> None:
        from plexctl.converters import similar_media_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CsvSimilarMedia

        media = [
            SimilarMedia(
                key="200", title="Tenet", media_type=MediaType.MOVIE, year=2020, similarity=85
            )
        ]
        rows = [similar_media_to_csv(m) for m in media]
        csv_content = to_csv(rows)

        restored = from_csv(CsvSimilarMedia, csv_content)
        assert len(restored) == 1
        assert restored[0].key == "200"
        assert restored[0].title == "Tenet"


# --- CSV model registry tests -------------------------------------------------


class TestSearchCsvModelRegistry:
    """Tests that search CSV models are registered for ingest."""

    def test_search_result_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvSearchResult

        cls = get_model_class("search_result")
        assert cls is not None
        assert cls is CsvSearchResult

    def test_similar_media_registered(self) -> None:
        from plexctl.csv_utils import get_model_class
        from plexctl.models import CsvSimilarMedia

        cls = get_model_class("similar_media")
        assert cls is not None
        assert cls is CsvSimilarMedia
