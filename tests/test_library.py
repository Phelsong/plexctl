"""Tests for LibraryService — section CRUD, locations, and collection operations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from plexctl.models import (
    CollectionInfo,
    CollectionMetadata,
    LibraryLocation,
    LibrarySection,
    MediaType,
)
from plexctl.services.library import LibraryService, _safe_bool, _safe_int_or

# --- Section CRUD tests ---------------------------------------------------------


class TestCreateSection:
    """Tests for LibraryService.create_section."""

    def test_create_section_with_valid_params(self) -> None:
        """create_section sends correct params and returns a LibrarySection."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)

            with patch.object(service, "list_sections") as mock_list:
                mock_list.return_value = [
                    LibrarySection(
                        key="7",
                        title="New Movies",
                        section_type=MediaType.MOVIE,
                        agent="com.plexapp.agents.imdb",
                        scanner="Plex Movie Scanner",
                        language="en",
                        count=0,
                    )
                ]

                result = service.create_section(
                    name="New Movies",
                    section_type="movie",
                    agent="com.plexapp.agents.imdb",
                    location_path="/data/movies",
                )

        assert isinstance(result, LibrarySection)
        assert result.title == "New Movies"
        assert result.section_type == MediaType.MOVIE
        mock_http.post.assert_called_once()

    def test_create_section_requires_name(self) -> None:
        """create_section raises ValueError when name is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Section name is required"):
                service.create_section(
                    name="",
                    section_type="movie",
                    agent="com.plexapp.agents.imdb",
                    location_path="/data/movies",
                )

    def test_create_section_requires_type(self) -> None:
        """create_section raises ValueError when type is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Section type is required"):
                service.create_section(
                    name="Movies",
                    section_type="",
                    agent="com.plexapp.agents.imdb",
                    location_path="/data/movies",
                )

    def test_create_section_requires_agent(self) -> None:
        """create_section raises ValueError when agent is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Metadata agent is required"):
                service.create_section(
                    name="Movies", section_type="movie", agent="", location_path="/data/movies"
                )

    def test_create_section_requires_location(self) -> None:
        """create_section raises ValueError when location is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Location path is required"):
                service.create_section(
                    name="Movies",
                    section_type="movie",
                    agent="com.plexapp.agents.imdb",
                    location_path="",
                )

    def test_create_section_default_scanner_movie(self) -> None:
        """create_section uses Plex Movie Scanner for movie type."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)

            with patch.object(service, "list_sections") as mock_list:
                mock_list.return_value = [
                    LibrarySection(
                        key="7",
                        title="Movies",
                        section_type=MediaType.MOVIE,
                        agent="com.plexapp.agents.imdb",
                        scanner="Plex Movie Scanner",
                        language="en",
                        count=0,
                    )
                ]
                result = service.create_section(
                    name="Movies",
                    section_type="movie",
                    agent="com.plexapp.agents.imdb",
                    location_path="/data/movies",
                )

        assert result.scanner == "Plex Movie Scanner"

    def test_create_section_default_scanner_show(self) -> None:
        """create_section uses Plex Series Scanner for show type."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)

            with patch.object(service, "list_sections") as mock_list:
                mock_list.return_value = [
                    LibrarySection(
                        key="2",
                        title="TV Shows",
                        section_type=MediaType.SHOW,
                        agent="com.plexapp.agents.thetvdb",
                        scanner="Plex Series Scanner",
                        language="en",
                        count=0,
                    )
                ]
                result = service.create_section(
                    name="TV Shows",
                    section_type="show",
                    agent="com.plexapp.agents.thetvdb",
                    location_path="/data/tv",
                )

        assert result.scanner == "Plex Series Scanner"

    def test_create_section_custom_scanner(self) -> None:
        """create_section uses provided scanner when specified."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)

            with patch.object(service, "list_sections") as mock_list:
                mock_list.return_value = [
                    LibrarySection(
                        key="3",
                        title="Anime",
                        section_type=MediaType.SHOW,
                        agent="com.plexapp.agents.thetvdb",
                        scanner="Shoko Relay Scanner",
                        language="en",
                        count=0,
                    )
                ]
                result = service.create_section(
                    name="Anime",
                    section_type="show",
                    agent="com.plexapp.agents.thetvdb",
                    location_path="/data/anime",
                    scanner="Shoko Relay Scanner",
                )

        assert result.scanner == "Shoko Relay Scanner"


class TestListSections:
    """Tests for LibraryService.list_sections."""

    def test_list_sections_returns_sections(self) -> None:
        """list_sections parses API response into LibrarySection models."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Directory": [
                    {
                        "key": "1",
                        "title": "Movies",
                        "type": "movie",
                        "agent": "com.plexapp.agents.imdb",
                        "scanner": "Plex Movie Scanner",
                        "language": "en",
                        "totalSize": 500,
                    },
                    {
                        "key": "2",
                        "title": "TV Shows",
                        "type": "show",
                        "agent": "com.plexapp.agents.thetvdb",
                        "scanner": "Plex Series Scanner",
                        "language": "en",
                        "leafCount": 1200,
                    },
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            sections = service.list_sections()

        assert len(sections) == 2
        assert sections[0].key == "1"
        assert sections[0].title == "Movies"
        assert sections[0].section_type == MediaType.MOVIE
        assert sections[0].agent == "com.plexapp.agents.imdb"
        assert sections[0].scanner == "Plex Movie Scanner"
        assert sections[0].count == 500

        assert sections[1].key == "2"
        assert sections[1].title == "TV Shows"
        assert sections[1].section_type == MediaType.SHOW
        assert sections[1].count == 1200

    def test_list_sections_empty_response(self) -> None:
        """list_sections returns empty list when no sections."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Directory": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            sections = service.list_sections()
        assert sections == []

    def test_list_sections_none_response(self) -> None:
        """list_sections returns empty list when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            sections = service.list_sections()
        assert sections == []

    def test_list_sections_single_dict_response(self) -> None:
        """list_sections handles single dict instead of list from API."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Directory": {
                    "key": "1",
                    "title": "Movies",
                    "type": "movie",
                    "agent": "agent",
                    "scanner": "scanner",
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            sections = service.list_sections()
        assert len(sections) == 1
        assert sections[0].title == "Movies"

    def test_list_sections_unknown_type(self) -> None:
        """list_sections handles unknown section types gracefully."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Directory": [
                    {
                        "key": "3",
                        "title": "Books",
                        "type": "book",
                        "agent": "agent",
                        "scanner": "scanner",
                    }
                ]
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            sections = service.list_sections()
        assert len(sections) == 1
        assert sections[0].section_type is None

    def test_list_sections_calls_correct_endpoint(self) -> None:
        """list_sections calls GET /library/sections."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Directory": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.list_sections()
        mock_http.get.assert_called_once_with("/library/sections")


class TestGetSection:
    """Tests for LibraryService.get_section."""

    def test_get_section_returns_section(self) -> None:
        """get_section parses single section response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Directory": {
                    "key": "2",
                    "title": "TV Shows",
                    "type": "show",
                    "agent": "com.plexapp.agents.thetvdb",
                    "scanner": "Plex Series Scanner",
                    "language": "en",
                    "totalSize": 1200,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            section = service.get_section(2)
        assert section is not None
        assert section.key == "2"
        assert section.title == "TV Shows"
        assert section.section_type == MediaType.SHOW

    def test_get_section_not_found(self) -> None:
        """get_section returns None when section doesn't exist."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            section = service.get_section(999)
        assert section is None

    def test_get_section_none_response(self) -> None:
        """get_section returns None when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            section = service.get_section(1)
        assert section is None

    def test_get_section_list_response(self) -> None:
        """get_section handles list response (takes first item)."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            section = service.get_section(1)
        assert section is not None
        assert section.title == "Movies"

    def test_get_section_calls_correct_endpoint(self) -> None:
        """get_section calls GET /library/sections/{key}."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.get_section(5)
        mock_http.get.assert_called_once_with("/library/sections/5")


class TestDeleteSection:
    """Tests for LibraryService.delete_section."""

    def test_delete_section_calls_delete_endpoint(self) -> None:
        """delete_section sends DELETE to the correct endpoint."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.delete_section(2)
        mock_http.delete.assert_called_once_with("/library/sections/2")

    def test_delete_section_string_key(self) -> None:
        """delete_section handles string keys."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.delete_section("5")
        mock_http.delete.assert_called_once_with("/library/sections/5")


# --- Collection tests ----------------------------------------------------------


class TestListCollections:
    """Tests for LibraryService.list_collections."""

    def test_list_collections_without_section(self) -> None:
        """list_collections iterates all sections when no section_key."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        collections_data = {
            "MediaContainer": {
                "Metadata": [
                    {"ratingKey": "100", "title": "Best Movies", "smart": 0, "childCount": 15},
                    {
                        "ratingKey": "101",
                        "title": "Smart Collection",
                        "smart": 1,
                        "childCount": 30,
                    },
                ]
            }
        }

        sections = [
            LibrarySection(key="1", title="Movies"),
            LibrarySection(key="2", title="TV Shows"),
        ]

        with (
            patch("plexctl.client.PlexHTTPClient", return_value=mock_http),
            patch.object(LibraryService, "list_sections", return_value=sections),
        ):
            service = LibraryService(mock_client)
            # http.get is called per-section: first returns collections, second empty
            mock_http.get.side_effect = [collections_data, {"MediaContainer": {"Metadata": []}}]
            collections = service.list_collections()

        assert len(collections) == 2
        assert collections[0].key == "100"
        assert collections[0].title == "Best Movies"
        assert collections[0].smart is False
        assert collections[0].content_count == 15
        assert collections[0].section_title == "Movies"

        assert collections[1].key == "101"
        assert collections[1].title == "Smart Collection"
        assert collections[1].smart is True
        assert collections[1].content_count == 30
        assert collections[1].section_title == "Movies"

        calls = mock_http.get.call_args_list
        assert calls[0].args[0] == "/library/sections/1/collections"
        assert calls[1].args[0] == "/library/sections/2/collections"

    def test_list_collections_with_section(self) -> None:
        """list_collections filters by section when section_key provided."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.list_collections(section_key=2)
        mock_http.get.assert_called_once_with("/library/sections/2/collections")

    def test_list_collections_empty(self) -> None:
        """list_collections returns empty list when no collections."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        sections = [LibrarySection(key="1", title="Movies")]

        with (
            patch("plexctl.client.PlexHTTPClient", return_value=mock_http),
            patch.object(LibraryService, "list_sections", return_value=sections),
        ):
            mock_http.get.return_value = {"MediaContainer": {"Metadata": []}}
            service = LibraryService(mock_client)
            collections = service.list_collections()
        assert collections == []

    def test_list_collections_none_response(self) -> None:
        """list_collections returns empty list on None response."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        sections = [LibrarySection(key="1", title="Movies")]

        with (
            patch("plexctl.client.PlexHTTPClient", return_value=mock_http),
            patch.object(LibraryService, "list_sections", return_value=sections),
        ):
            mock_http.get.return_value = None
            service = LibraryService(mock_client)
            collections = service.list_collections()
        assert collections == []

    def test_list_collections_single_dict(self) -> None:
        """list_collections handles single dict metadata."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        collections_data = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "100",
                    "title": "Only Collection",
                    "smart": 0,
                    "childCount": 5,
                }
            }
        }

        sections = [LibrarySection(key="1", title="Movies")]

        with (
            patch("plexctl.client.PlexHTTPClient", return_value=mock_http),
            patch.object(LibraryService, "list_sections", return_value=sections),
        ):
            mock_http.get.return_value = collections_data
            service = LibraryService(mock_client)
            collections = service.list_collections()
        assert len(collections) == 1
        assert collections[0].title == "Only Collection"
        assert collections[0].section_title == "Movies"


class TestGetCollection:
    """Tests for LibraryService.get_collection."""

    def test_get_collection_returns_metadata(self) -> None:
        """get_collection parses collection detail response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "100",
                    "title": "Best Movies",
                    "smart": 0,
                    "childCount": 15,
                    "librarySectionID": "2",
                    "librarySectionTitle": "Movies",
                    "summary": "A great collection",
                    "thumb": "/library/metadata/100/thumb",
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            coll = service.get_collection(100)
        assert coll is not None
        assert coll.key == "100"
        assert coll.title == "Best Movies"
        assert coll.smart is False
        assert coll.content_count == 15
        assert coll.section_key == "2"
        assert coll.section_title == "Movies"
        assert coll.summary == "A great collection"
        assert coll.thumb == "/library/metadata/100/thumb"

    def test_get_collection_not_found(self) -> None:
        """get_collection returns None when collection not found."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Not found")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.get_collection(999)
        assert result is None

    def test_get_collection_none_response(self) -> None:
        """get_collection returns None on None response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.get_collection(100)
        assert result is None

    def test_get_collection_calls_correct_endpoint(self) -> None:
        """get_collection calls GET /library/metadata/{key}."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.get_collection(42)
        mock_http.get.assert_called_once_with("/library/metadata/42")


class TestCreateCollection:
    """Tests for LibraryService.create_collection."""

    def test_create_collection_requires_title(self) -> None:
        """create_collection raises ValueError when title is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Collection title is required"):
                service.create_collection(title="", section_key=2)

    def test_create_collection_requires_section_key(self) -> None:
        """create_collection raises ValueError when section_key is empty."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            with pytest.raises(ValueError, match="Section key is required"):
                service.create_collection(title="My Collection", section_key="")

    def test_create_collection_with_api_response(self) -> None:
        """create_collection returns CollectionMetadata from API response."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = {
            "MediaContainer": {"Metadata": {"ratingKey": "200", "title": "New Collection"}}
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.create_collection(title="New Collection", section_key=2)

        assert result.key == "200"
        assert result.title == "New Collection"
        assert result.section_key == "2"
        assert result.smart is False

    def test_create_collection_fallback_when_no_response(self) -> None:
        """create_collection returns fallback metadata when API returns None."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.create_collection(title="Fallback Collection", section_key=3)

        assert result.title == "Fallback Collection"
        assert result.key == ""
        assert result.section_key == "3"

    def test_create_collection_smart_flag(self) -> None:
        """create_collection passes smart flag and calls correct endpoint."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.post.return_value = None

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.create_collection(title="Smart Coll", section_key=1, smart=True)

        assert result.smart is True
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert "/library/sections/1/collections" in call_args[0][0]


class TestUpdateCollection:
    """Tests for LibraryService.update_collection."""

    def test_update_collection_with_title(self) -> None:
        """update_collection sends PUT with new title and returns updated data."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "100",
                    "title": "Updated Title",
                    "smart": 0,
                    "childCount": 15,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.update_collection(100, title="Updated Title")

        assert result is not None
        assert result.title == "Updated Title"
        mock_http.put.assert_called_once()
        mock_http.get.assert_called_once_with("/library/metadata/100")

    def test_update_collection_with_summary(self) -> None:
        """update_collection sends PUT with new summary."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {
                    "ratingKey": "100",
                    "title": "Collection",
                    "smart": 0,
                    "childCount": 15,
                }
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.update_collection(100, summary="New description")

        assert result is not None
        mock_http.put.assert_called_once()

    def test_update_collection_no_changes_fetches_current(self) -> None:
        """update_collection with no changes fetches current state."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.get.return_value = {
            "MediaContainer": {
                "Metadata": {"ratingKey": "100", "title": "Existing", "smart": 0, "childCount": 5}
            }
        }

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.update_collection(100)

        assert result is not None
        assert result.title == "Existing"
        # PUT should NOT have been called since no params
        mock_http.put.assert_not_called()
        # GET should have been called (for get_collection)
        mock_http.get.assert_called_once_with("/library/metadata/100")

    def test_update_collection_put_failure(self) -> None:
        """update_collection returns None when PUT fails."""
        mock_client = MagicMock()
        mock_http = MagicMock()
        mock_http.put.side_effect = Exception("Server error")

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            result = service.update_collection(100, title="Fail")
        assert result is None


class TestDeleteCollection:
    """Tests for LibraryService.delete_collection."""

    def test_delete_collection_calls_delete(self) -> None:
        """delete_collection sends DELETE to the correct endpoint."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.delete_collection(100)
        mock_http.delete.assert_called_once_with("/library/metadata/100")

    def test_delete_collection_string_key(self) -> None:
        """delete_collection handles string keys."""
        mock_client = MagicMock()
        mock_http = MagicMock()

        with patch("plexctl.client.PlexHTTPClient", return_value=mock_http):
            service = LibraryService(mock_client)
            service.delete_collection("200")
        mock_http.delete.assert_called_once_with("/library/metadata/200")


# --- Helper function tests -----------------------------------------------------


class TestSafeIntOr:
    """Tests for _safe_int_or helper."""

    def test_safe_int_or_with_int(self) -> None:
        assert _safe_int_or(42) == 42

    def test_safe_int_or_with_string(self) -> None:
        assert _safe_int_or("100") == 100

    def test_safe_int_or_with_none(self) -> None:
        assert _safe_int_or(None) == 0

    def test_safe_int_or_with_empty_string(self) -> None:
        assert _safe_int_or("") == 0

    def test_safe_int_or_with_default(self) -> None:
        assert _safe_int_or(None, default=-1) == -1

    def test_safe_int_or_with_invalid(self) -> None:
        assert _safe_int_or("not_a_number") == 0


class TestSafeBool:
    """Tests for _safe_bool helper."""

    def test_safe_bool_with_true(self) -> None:
        assert _safe_bool(True) is True

    def test_safe_bool_with_false(self) -> None:
        assert _safe_bool(False) is False

    def test_safe_bool_with_int_1(self) -> None:
        assert _safe_bool(1) is True

    def test_safe_bool_with_int_0(self) -> None:
        assert _safe_bool(0) is False

    def test_safe_bool_with_string_true(self) -> None:
        assert _safe_bool("true") is True
        assert _safe_bool("True") is True
        assert _safe_bool("1") is True
        assert _safe_bool("yes") is True

    def test_safe_bool_with_string_false(self) -> None:
        assert _safe_bool("false") is False
        assert _safe_bool("0") is False
        assert _safe_bool("no") is False

    def test_safe_bool_with_none(self) -> None:
        assert _safe_bool(None) is False

    def test_safe_bool_with_other_type(self) -> None:
        assert _safe_bool(3.14) is False


# --- Model tests ---------------------------------------------------------------


class TestLibraryLocationModel:
    """Tests for LibraryLocation model."""

    def test_library_location_creation(self) -> None:
        loc = LibraryLocation(id=1, path="/data/anime")
        assert loc.id == 1
        assert loc.path == "/data/anime"

    def test_library_location_defaults(self) -> None:
        loc = LibraryLocation(id=0, path="")
        assert loc.id == 0
        assert loc.path == ""


class TestMediaTreeItemModel:
    """Tests for MediaTreeItem model."""

    def test_media_tree_item_minimal(self) -> None:
        from plexctl.models import MediaTreeItem

        item = MediaTreeItem(key="12345")
        assert item.key == "12345"
        assert item.title is None
        assert item.media_type is None
        assert item.children == []

    def test_media_tree_item_full(self) -> None:
        from plexctl.models import MediaTreeItem, MediaType

        child = MediaTreeItem(key="200", title="Episode 1", media_type=MediaType.EPISODE)
        item = MediaTreeItem(
            key="100",
            title="Test Show",
            media_type=MediaType.SHOW,
            year=2024,
            leaf_count=24,
            viewed_leaf_count=12,
            children=[child],
        )
        assert item.title == "Test Show"
        assert item.media_type == MediaType.SHOW
        assert item.year == 2024
        assert item.leaf_count == 24
        assert len(item.children) == 1
        assert item.children[0].title == "Episode 1"


class TestCollectionMetadataModel:
    """Tests for CollectionMetadata model."""

    def test_collection_metadata_minimal(self) -> None:
        coll = CollectionMetadata(key="100", title="My Collection")
        assert coll.key == "100"
        assert coll.title == "My Collection"
        assert coll.smart is False
        assert coll.content_count == 0
        assert coll.section_key is None
        assert coll.summary is None

    def test_collection_metadata_full(self) -> None:
        coll = CollectionMetadata(
            key="100",
            title="Best Movies",
            smart=True,
            content_count=30,
            section_key="2",
            section_title="Movies",
            summary="A collection of the best movies",
            thumb="/thumb/100",
            art="/art/100",
            added_at="1234567890",
            updated_at="1234567899",
        )
        assert coll.smart is True
        assert coll.content_count == 30
        assert coll.summary == "A collection of the best movies"

    def test_collection_info_model(self) -> None:
        info = CollectionInfo(
            key="100", title="My Coll", smart=False, content_count=10, section_title="Movies"
        )
        assert info.key == "100"
        assert info.section_title == "Movies"
