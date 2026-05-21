"""Tests for CLI commands — library and item command validation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from plexctl.cli import app
from typer.testing import CliRunner

runner = CliRunner()


# --- Library commands ----------------------------------------------------------


class TestLibraryListCommand:
    """Tests for 'plexctl library list' CLI command."""

    @patch("plexctl.commands.library.PlexClient")
    @patch("plexctl.commands.library.load_config")
    def test_library_list_no_sections(self, mock_config, mock_client_cls) -> None:
        """library list shows message when no sections exist."""
        from plexctl.config import PlexConfig
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Need to mock the service to return empty list
        with patch.object(LibraryService, "list_sections", return_value=[]):
            result = runner.invoke(app, ["library", "list"])

        # Should run without error (may show "no sections" message)
        assert result.exit_code == 0

    @patch("plexctl.commands.library.PlexClient")
    @patch("plexctl.commands.library.load_config")
    def test_library_list_with_sections(self, mock_config, mock_client_cls) -> None:
        """library list displays section table."""
        from plexctl.config import PlexConfig
        from plexctl.models import LibrarySection, MediaType
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        sections = [
            LibrarySection(
                key="1",
                title="Movies",
                section_type=MediaType.MOVIE,
                agent="com.plexapp.agents.imdb",
                scanner="Plex Movie Scanner",
                language="en",
                count=500,
            )
        ]

        with patch.object(LibraryService, "list_sections", return_value=sections):
            result = runner.invoke(app, ["library", "list"])

        assert result.exit_code == 0
        assert "Movies" in result.output

    @patch("plexctl.commands.library.PlexClient")
    @patch("plexctl.commands.library.load_config")
    def test_library_list_csv_output(self, mock_config, mock_client_cls) -> None:
        """library list --csv outputs CSV format."""
        from plexctl.config import PlexConfig
        from plexctl.models import LibrarySection, MediaType
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        sections = [
            LibrarySection(
                key="1",
                title="Movies",
                section_type=MediaType.MOVIE,
                agent="com.plexapp.agents.imdb",
                scanner="Plex Movie Scanner",
                language="en",
                count=500,
            )
        ]

        with patch.object(LibraryService, "list_sections", return_value=sections):
            result = runner.invoke(app, ["library", "list", "--csv"])

        assert result.exit_code == 0
        assert "key" in result.output
        assert "Movies" in result.output


class TestLibraryDeleteCommand:
    """Tests for 'plexctl library delete' CLI command."""

    def test_library_delete_requires_confirmation(self) -> None:
        """library delete requires --yes flag."""
        result = runner.invoke(app, ["library", "delete", "2"])
        # Should fail without --yes
        assert result.exit_code == 1
        assert "confirm" in result.output.lower() or "yes" in result.output.lower()

    @patch("plexctl.commands.library.PlexClient")
    @patch("plexctl.commands.library.load_config")
    def test_library_delete_with_confirmation(
        self, mock_config, mock_client_cls
    ) -> None:
        """library delete --yes calls delete_section."""
        from plexctl.config import PlexConfig
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(LibraryService, "delete_section") as mock_delete:
            result = runner.invoke(app, ["library", "delete", "2", "--yes"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with("2")


class TestLibraryCreateCommand:
    """Tests for 'plexctl library create' CLI command."""

    @patch("plexctl.commands.library.PlexClient")
    @patch("plexctl.commands.library.load_config")
    def test_library_create_calls_service(self, mock_config, mock_client_cls) -> None:
        """library create calls create_section with correct params."""
        from plexctl.config import PlexConfig
        from plexctl.models import LibrarySection, MediaType
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        new_section = LibrarySection(
            key="7",
            title="New Movies",
            section_type=MediaType.MOVIE,
            agent="com.plexapp.agents.imdb",
            scanner="Plex Movie Scanner",
            language="en",
            count=0,
        )

        with patch.object(
            LibraryService, "create_section", return_value=new_section
        ) as mock_create:
            result = runner.invoke(
                app,
                [
                    "library",
                    "create",
                    "--name",
                    "New Movies",
                    "--type",
                    "movie",
                    "--agent",
                    "com.plexapp.agents.imdb",
                    "--location",
                    "/data/movies",
                ],
            )

        assert result.exit_code == 0
        mock_create.assert_called_once_with(
            name="New Movies",
            section_type="movie",
            agent="com.plexapp.agents.imdb",
            location_path="/data/movies",
            language="en",
            scanner=None,
        )


# --- Collection commands (via library) -----------------------------------------


class TestCollectionListCommand:
    """Tests for 'plexctl library collections list' CLI command."""

    @patch("plexctl.commands.collections.PlexClient")
    @patch("plexctl.commands.collections.load_config")
    def test_collection_list_empty(self, mock_config, mock_client_cls) -> None:
        """library collections list shows message when no collections exist."""
        from plexctl.config import PlexConfig
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(LibraryService, "list_collections", return_value=[]):
            result = runner.invoke(app, ["library", "collections", "list"])

        assert result.exit_code == 0

    @patch("plexctl.commands.collections.PlexClient")
    @patch("plexctl.commands.collections.load_config")
    def test_collection_list_with_items(self, mock_config, mock_client_cls) -> None:
        """library collections list displays collection table."""
        from plexctl.config import PlexConfig
        from plexctl.models import CollectionInfo
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        collections = [
            CollectionInfo(
                key="100", title="Best Movies", smart=False, content_count=15
            )
        ]

        with patch.object(LibraryService, "list_collections", return_value=collections):
            result = runner.invoke(app, ["library", "collections", "list"])

        assert result.exit_code == 0
        assert "Best Movies" in result.output

    @patch("plexctl.commands.collections.PlexClient")
    @patch("plexctl.commands.collections.load_config")
    def test_collection_list_csv(self, mock_config, mock_client_cls) -> None:
        """library collections list --csv outputs CSV format."""
        from plexctl.config import PlexConfig
        from plexctl.models import CollectionInfo
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        collections = [
            CollectionInfo(
                key="100", title="Best Movies", smart=False, content_count=15
            )
        ]

        with patch.object(LibraryService, "list_collections", return_value=collections):
            result = runner.invoke(app, ["library", "collections", "list", "--csv"])

        assert result.exit_code == 0
        assert "key" in result.output
        assert "Best Movies" in result.output


class TestCollectionDeleteCommand:
    """Tests for 'plexctl library collections delete' CLI command."""

    def test_collection_delete_requires_confirmation(self) -> None:
        """library collections delete requires --yes flag."""
        result = runner.invoke(app, ["library", "collections", "delete", "100"])
        assert result.exit_code == 1

    @patch("plexctl.commands.collections.PlexClient")
    @patch("plexctl.commands.collections.load_config")
    def test_collection_delete_with_confirmation(
        self, mock_config, mock_client_cls
    ) -> None:
        """library collections delete --yes calls delete_collection."""
        from plexctl.config import PlexConfig
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with patch.object(LibraryService, "delete_collection") as mock_delete:
            result = runner.invoke(
                app, ["library", "collections", "delete", "100", "--yes"]
            )

        assert result.exit_code == 0
        mock_delete.assert_called_once_with("100")


class TestCollectionUpdateCommand:
    """Tests for 'plexctl library collections update' CLI command."""

    def test_collection_update_requires_option(self) -> None:
        """library collections update requires at least --title or --summary."""
        result = runner.invoke(app, ["library", "collections", "update", "100"])
        assert result.exit_code == 1

    @patch("plexctl.commands.collections.PlexClient")
    @patch("plexctl.commands.collections.load_config")
    def test_collection_update_with_title(self, mock_config, mock_client_cls) -> None:
        """library collections update --title calls update_collection."""
        from plexctl.config import PlexConfig
        from plexctl.models import CollectionMetadata
        from plexctl.services.library import LibraryService

        mock_config.return_value = PlexConfig(
            url="http://localhost:32400", token="test-token"
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        updated = CollectionMetadata(
            key="100", title="Updated Title", smart=False, content_count=15
        )

        with patch.object(
            LibraryService, "update_collection", return_value=updated
        ) as mock_update:
            result = runner.invoke(
                app,
                ["library", "collections", "update", "100", "--title", "Updated Title"],
            )

        assert result.exit_code == 0
        mock_update.assert_called_once_with("100", title="Updated Title", summary=None)


# --- CSV converter tests -------------------------------------------------------


class TestLibraryConverters:
    """Tests for library-related CSV converters."""

    def test_library_section_to_csv(self) -> None:
        """library_section_to_csv converts correctly."""
        from plexctl.converters import library_section_to_csv
        from plexctl.models import LibrarySection, MediaType

        section = LibrarySection(
            key="1",
            title="Movies",
            section_type=MediaType.MOVIE,
            agent="com.plexapp.agents.imdb",
            scanner="Plex Movie Scanner",
            language="en",
            count=500,
        )
        csv_row = library_section_to_csv(section)
        assert csv_row.key == "1"
        assert csv_row.title == "Movies"
        assert csv_row.section_type == "movie"
        assert csv_row.agent == "com.plexapp.agents.imdb"
        assert csv_row.scanner == "Plex Movie Scanner"
        assert csv_row.language == "en"
        assert csv_row.count == "500"

    def test_library_section_to_csv_none_type(self) -> None:
        """library_section_to_csv handles None section_type."""
        from plexctl.converters import library_section_to_csv
        from plexctl.models import LibrarySection

        section = LibrarySection(key="3", title="Books", section_type=None)
        csv_row = library_section_to_csv(section)
        assert csv_row.section_type == ""

    def test_library_location_to_csv(self) -> None:
        """library_location_to_csv converts correctly."""
        from plexctl.converters import library_location_to_csv
        from plexctl.models import LibraryLocation

        loc = LibraryLocation(id=1, path="/data/anime")
        csv_row = library_location_to_csv(loc)
        assert csv_row.id == "1"
        assert csv_row.path == "/data/anime"

    def test_media_tree_item_to_csv(self) -> None:
        """media_tree_item_to_csv converts correctly."""
        from plexctl.converters import media_tree_item_to_csv
        from plexctl.models import MediaTreeItem, MediaType

        item = MediaTreeItem(
            key="100",
            title="Arifureta",
            media_type=MediaType.SHOW,
            year=2019,
            leaf_count=24,
            viewed_leaf_count=12,
        )
        csv_row = media_tree_item_to_csv(item)
        assert csv_row.key == "100"
        assert csv_row.title == "Arifureta"
        assert csv_row.media_type == "show"
        assert csv_row.year == "2019"
        assert csv_row.leaf_count == "24"
        assert csv_row.viewed_leaf_count == "12"
        assert csv_row.children == ""

    def test_media_tree_item_to_csv_with_children(self) -> None:
        """media_tree_item_to_csv summarizes children."""
        from plexctl.converters import media_tree_item_to_csv
        from plexctl.models import MediaTreeItem, MediaType

        child = MediaTreeItem(key="110", title="Season 1")
        item = MediaTreeItem(
            key="100", title="Arifureta", media_type=MediaType.SHOW, children=[child]
        )
        csv_row = media_tree_item_to_csv(item)
        assert "Season 1" in csv_row.children
        assert "110" in csv_row.children

    def test_media_tree_item_to_csv_none_fields(self) -> None:
        """media_tree_item_to_csv handles None fields."""
        from plexctl.converters import media_tree_item_to_csv
        from plexctl.models import MediaTreeItem

        item = MediaTreeItem(key="100")
        csv_row = media_tree_item_to_csv(item)
        assert csv_row.title == ""
        assert csv_row.media_type == ""
        assert csv_row.year == ""
        assert csv_row.leaf_count == ""

    def test_collection_metadata_to_csv(self) -> None:
        """collection_metadata_to_csv converts correctly."""
        from plexctl.converters import collection_metadata_to_csv
        from plexctl.models import CollectionMetadata

        coll = CollectionMetadata(
            key="100",
            title="Best Movies",
            smart=True,
            content_count=30,
            section_key="2",
            section_title="Movies",
            summary="A great collection of movies",
        )
        csv_row = collection_metadata_to_csv(coll)
        assert csv_row.key == "100"
        assert csv_row.title == "Best Movies"
        assert csv_row.smart == "True"
        assert csv_row.content_count == "30"
        assert csv_row.section_key == "2"
        assert csv_row.section_title == "Movies"
        assert "great collection" in csv_row.summary

    def test_collection_metadata_to_csv_multiline_summary(self) -> None:
        """collection_metadata_to_csv strips newlines from summary."""
        from plexctl.converters import collection_metadata_to_csv
        from plexctl.models import CollectionMetadata

        coll = CollectionMetadata(
            key="100", title="Test", summary="Line 1\nLine 2\nLine 3"
        )
        csv_row = collection_metadata_to_csv(coll)
        assert "\n" not in csv_row.summary
        assert "Line 1" in csv_row.summary


# --- CSV model registry tests --------------------------------------------------


class TestNewCsvModelRegistry:
    """Tests that new CSV models are registered for ingest."""

    def test_library_location_registered(self) -> None:
        """library_location model is registered for ingest."""
        from plexctl.csv_utils import get_model_class

        cls = get_model_class("library_location")
        assert cls is not None
        from plexctl.models import CsvLibraryLocation

        assert cls is CsvLibraryLocation

    def test_media_tree_item_registered(self) -> None:
        """media_tree_item model is registered for ingest."""
        from plexctl.csv_utils import get_model_class

        cls = get_model_class("media_tree_item")
        assert cls is not None
        from plexctl.models import CsvMediaTreeItem

        assert cls is CsvMediaTreeItem

    def test_collection_metadata_registered(self) -> None:
        """collection_metadata model is registered for ingest."""
        from plexctl.csv_utils import get_model_class

        cls = get_model_class("collection_metadata")
        assert cls is not None
        from plexctl.models import CsvCollectionMetadata

        assert cls is CsvCollectionMetadata


# --- CSV roundtrip tests -------------------------------------------------------


class TestCsvRoundtrip:
    """Tests that new models survive CSV roundtrip."""

    def test_library_location_roundtrip(self) -> None:
        """LibraryLocation CSV roundtrip preserves data."""
        from plexctl.converters import library_location_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import LibraryLocation

        locations = [
            LibraryLocation(id=1, path="/data/anime"),
            LibraryLocation(id=2, path="/data/movies"),
        ]
        rows = [library_location_to_csv(loc) for loc in locations]
        csv_content = to_csv(rows)

        from plexctl.models import CsvLibraryLocation

        restored = from_csv(CsvLibraryLocation, csv_content)
        assert len(restored) == 2
        assert restored[0].path == "/data/anime"
        assert restored[1].path == "/data/movies"

    def test_library_section_roundtrip(self) -> None:
        """LibrarySection CSV roundtrip preserves data."""
        from plexctl.converters import library_section_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import LibrarySection, MediaType

        sections = [
            LibrarySection(
                key="1",
                title="Movies",
                section_type=MediaType.MOVIE,
                agent="agent1",
                scanner="scanner1",
                language="en",
                count=500,
            ),
            LibrarySection(
                key="2",
                title="TV Shows",
                section_type=MediaType.SHOW,
                agent="agent2",
                scanner="scanner2",
                language="en",
                count=1200,
            ),
        ]
        rows = [library_section_to_csv(s) for s in sections]
        csv_content = to_csv(rows)

        from plexctl.models import CsvLibrarySection

        restored = from_csv(CsvLibrarySection, csv_content)
        assert len(restored) == 2
        assert restored[0].title == "Movies"
        assert restored[0].section_type == "movie"
        assert restored[0].agent == "agent1"
        assert restored[1].title == "TV Shows"

    def test_collection_metadata_roundtrip(self) -> None:
        """CollectionMetadata CSV roundtrip preserves data."""
        from plexctl.converters import collection_metadata_to_csv
        from plexctl.csv_utils import from_csv, to_csv
        from plexctl.models import CollectionMetadata

        collections = [
            CollectionMetadata(
                key="100",
                title="Best Movies",
                smart=True,
                content_count=30,
                section_key="2",
                section_title="Movies",
                summary="A great collection",
            )
        ]
        rows = [collection_metadata_to_csv(c) for c in collections]
        csv_content = to_csv(rows)

        from plexctl.models import CsvCollectionMetadata

        restored = from_csv(CsvCollectionMetadata, csv_content)
        assert len(restored) == 1
        assert restored[0].key == "100"
        assert restored[0].title == "Best Movies"
        assert restored[0].smart == "True"
        assert restored[0].content_count == "30"
