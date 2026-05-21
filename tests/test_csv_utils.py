"""Tests for CSV serialization and deserialization."""
from pathlib import Path

from plexctl.csv_utils import from_csv, get_model_class, list_model_names, to_csv
from plexctl.models import CsvLibrarySection, CsvTriageIssue


class TestToCsv:
    """Test CSV serialization of Pydantic models."""

    def test_to_csv_empty_list(self) -> None:
        """Empty model list produces empty CSV string."""
        result = to_csv([])
        assert result == ""

    def test_to_csv_single_model(self) -> None:
        """Single model serializes to CSV with headers."""
        section = CsvLibrarySection(key="1", title="Movies")
        result = to_csv([section])
        lines = result.strip().split("\n")
        assert len(lines) == 2  # header + data
        assert "key" in lines[0]
        assert "title" in lines[0]

    def test_to_csv_multiple_models(self) -> None:
        """Multiple models serialize with one row each."""
        sections = [
            CsvLibrarySection(key="1", title="Movies"),
            CsvLibrarySection(key="2", title="TV Shows"),
        ]
        result = to_csv(sections)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_to_csv_no_headers(self) -> None:
        """include_headers=False omits header row."""
        section = CsvLibrarySection(key="1", title="Movies")
        result = to_csv([section], include_headers=False)
        assert "key" not in result
        assert "1" in result

    def test_to_csv_file_output(self, tmp_path: Path) -> None:
        """to_csv writes to file when output path is provided."""
        section = CsvLibrarySection(key="1", title="Movies")
        output = tmp_path / "test.csv"
        to_csv([section], output=output)
        assert output.exists()
        content = output.read_text()
        assert "Movies" in content


class TestFromCsv:
    """Test CSV deserialization back into Pydantic models."""

    def test_from_csv_string(self) -> None:
        """CSV string deserializes into model instances."""
        csv_data = "key,title\n1,Movies\n2,TV Shows\n"
        models = from_csv(CsvLibrarySection, csv_data)
        assert len(models) == 2
        assert models[0].key == "1"
        assert models[0].title == "Movies"
        assert models[1].key == "2"
        assert models[1].title == "TV Shows"

    def test_from_csv_file(self, tmp_path: Path) -> None:
        """CSV file path deserializes into model instances."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("key,title\n1,Movies\n2,TV Shows\n")
        models = from_csv(CsvLibrarySection, csv_path)
        assert len(models) == 2
        assert models[0].title == "Movies"

    def test_from_csv_empty(self) -> None:
        """Empty CSV string returns empty list."""
        models = from_csv(CsvLibrarySection, "")
        assert models == []

    def test_from_csv_whitespace_only(self) -> None:
        """Whitespace-only CSV string returns empty list."""
        models = from_csv(CsvLibrarySection, "   \n\n   ")
        assert models == []

    def test_from_csv_optional_fields(self) -> None:
        """Empty optional fields fall back to model defaults."""
        csv_data = "key,title,section_type,count\n1,Movies,,\n"
        models = from_csv(CsvLibrarySection, csv_data)
        assert len(models) == 1
        # Empty CSV cells are omitted; Pydantic defaults fill them in
        assert models[0].section_type == ""
        assert models[0].count == ""

    def test_roundtrip(self) -> None:
        """Data survives a to_csv -> from_csv roundtrip."""
        original = [
            CsvLibrarySection(key="1", title="Movies", section_type="movie", count="5"),
            CsvLibrarySection(
                key="2", title="TV Shows", section_type="show", count="50"
            ),
        ]
        csv_content = to_csv(original)
        restored = from_csv(CsvLibrarySection, csv_content)
        assert len(restored) == 2
        assert restored[0].key == "1"
        assert restored[0].title == "Movies"
        assert restored[1].key == "2"
        assert restored[1].title == "TV Shows"


class TestModelRegistry:
    """Test model registry for ingest command."""

    def test_list_model_names(self) -> None:
        """list_model_names returns sorted model names."""
        names = list_model_names()
        assert "triage_issue" in names
        assert "season_gap" in names
        assert "media_metadata" in names
        # Verify sorted
        assert names == sorted(names)

    def test_get_model_class_known(self) -> None:
        """Known model names return their class."""
        cls = get_model_class("triage_issue")
        assert cls is not None
        assert cls is CsvTriageIssue

    def test_get_model_class_unknown(self) -> None:
        """Unknown model names return None."""
        cls = get_model_class("nonexistent_model")
        assert cls is None

    def test_all_csv_models_registered(self) -> None:
        """All Csv* model names are in the registry."""
        names = list_model_names()
        expected = [
            "media_metadata",
            "library_section",
            "collection_info",
            "show_diagnostics",
            "triage_issue",
            "season_gap",
            "shoko_series",
            "shoko_file",
            "shoko_mismatch",
            "shoko_episode",
            "episode_diagnostics",
            "media_part_detail",
            "tmdb_search_result",
            "fs_dir",
        ]
        for name in expected:
            assert name in names, f"Model '{name}' not in registry"

    def test_registered_model_has_fields(self) -> None:
        """Each registered model class has model_fields."""
        for name in list_model_names():
            cls = get_model_class(name)
            assert cls is not None
            assert len(cls.model_fields) > 0, f"Model '{name}' has no fields"
