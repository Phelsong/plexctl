"""Tests for filesystem comparison models and service."""

from pathlib import Path

from plexctl.models import VIDEO_EXTENSIONS, FsCompareResult, FsDir
from plexctl.services.fs_compare import FsCompareService


class TestVideoExtensions:
    """Tests for VIDEO_EXTENSIONS constant."""

    def test_common_formats_included(self) -> None:
        assert ".mkv" in VIDEO_EXTENSIONS
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".avi" in VIDEO_EXTENSIONS
        assert ".webm" in VIDEO_EXTENSIONS

    def test_non_video_excluded(self) -> None:
        assert ".txt" not in VIDEO_EXTENSIONS
        assert ".jpg" not in VIDEO_EXTENSIONS
        assert ".nfo" not in VIDEO_EXTENSIONS

    def test_frozen_set(self) -> None:
        assert isinstance(VIDEO_EXTENSIONS, frozenset)


class TestFsDir:
    """Tests for FsDir model."""

    def test_basic_dir(self) -> None:
        d = FsDir(path="/mnt/nfs/media/anime/Arifureta", name="Arifureta")
        assert d.path == "/mnt/nfs/media/anime/Arifureta"
        assert d.name == "Arifureta"
        assert d.video_files == 0
        assert d.has_files is False
        assert d.subdir_count == 0
        assert d.subdirs == []
        assert d.is_plex_location is False
        assert d.plex_shows == []

    def test_dir_with_content(self) -> None:
        d = FsDir(
            path="/mnt/nfs/media/anime/One Piece",
            name="One Piece",
            video_files=1195,
            has_files=True,
            subdir_count=2,
            subdirs=["Season 01", "Season 02"],
            is_plex_location=True,
            plex_shows=["One Piece"],
        )
        assert d.video_files == 1195
        assert d.has_files is True
        assert d.subdir_count == 2
        assert d.is_plex_location is True

    def test_grouped_dir(self) -> None:
        """A dir with both files and subdirs is the ShokoRelay grouping pattern."""
        d = FsDir(
            path="/mnt/nfs/media/anime/Arifureta",
            name="Arifureta",
            video_files=12,
            has_files=True,
            subdir_count=3,
            subdirs=[
                "Arifureta: From Commonplace to World's Strongest",
                "Arifureta Shokugyou de Sekai Saikyou 2nd Season",
                "Arifureta: From Commonplace to World's Strongest Season 3",
            ],
            is_plex_location=True,
            plex_shows=["Arifureta"],
        )
        assert d.has_files is True and d.subdir_count > 0

    def test_has_files_without_count(self) -> None:
        """When count_files=False, has_files still detects grouping risk."""
        d = FsDir(
            path="/mnt/nfs/media/anime/Arifureta",
            name="Arifureta",
            video_files=0,  # Not counted
            has_files=True,  # But we know files exist
            subdir_count=3,
            subdirs=["Season 1", "Season 2", "Season 3"],
        )
        assert d.video_files == 0
        assert d.has_files is True
        assert d.subdir_count > 0


class TestFsCompareResult:
    """Tests for FsCompareResult model."""

    def test_empty_result(self) -> None:
        result = FsCompareResult(section_root="/mnt/nfs/media/anime", section_title="Anime")
        assert result.total_dirs == 0
        assert result.plex_tracked_dirs == 0
        assert result.orphan_dirs == []
        assert result.multi_location_shows == []
        assert result.grouped_dirs == []

    def test_with_orphans(self) -> None:
        orphan = FsDir(path="/mnt/nfs/media/anime/.temp", name=".temp", video_files=5)
        result = FsCompareResult(
            section_root="/mnt/nfs/media/anime",
            section_title="Anime",
            total_dirs=10,
            plex_tracked_dirs=8,
            orphan_dirs=[orphan],
        )
        assert len(result.orphan_dirs) == 1
        assert result.orphan_dirs[0].name == ".temp"

    def test_multi_location_shows(self) -> None:
        result = FsCompareResult(
            section_root="/mnt/nfs/media/anime",
            section_title="Anime",
            multi_location_shows=[
                (
                    "Sword Art Online",
                    [
                        "/mnt/nfs/media/anime/Sword Art Online",
                        "/mnt/nfs/media/anime/Sword Art Online Alicization",
                    ],
                )
            ],
        )
        assert len(result.multi_location_shows) == 1
        show_title, locations = result.multi_location_shows[0]
        assert show_title == "Sword Art Online"
        assert len(locations) == 2


class TestFsCompareServiceCountVideoFiles:
    """Tests for FsCompareService._count_video_files."""

    def test_count_video_files_empty_dir(self, tmp_path: Path) -> None:
        assert FsCompareService._count_video_files(tmp_path) == 0

    def test_count_video_files_with_videos(self, tmp_path: Path) -> None:
        (tmp_path / "episode01.mkv").touch()
        (tmp_path / "episode02.mp4").touch()
        (tmp_path / "readme.txt").touch()
        assert FsCompareService._count_video_files(tmp_path) == 2

    def test_count_video_files_nonexistent(self) -> None:
        assert FsCompareService._count_video_files(Path("/nonexistent/path")) == 0


class TestFsCompareServiceHasFiles:
    """Tests for FsCompareService._has_files."""

    def test_has_files_empty_dir(self, tmp_path: Path) -> None:
        assert FsCompareService._has_files(tmp_path) is False

    def test_has_files_with_regular_file(self, tmp_path: Path) -> None:
        (tmp_path / "episode.mkv").touch()
        assert FsCompareService._has_files(tmp_path) is True

    def test_has_files_with_non_video_file(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").touch()
        assert FsCompareService._has_files(tmp_path) is True

    def test_has_files_subdirs_only(self, tmp_path: Path) -> None:
        (tmp_path / "Season 01").mkdir()
        assert FsCompareService._has_files(tmp_path) is False

    def test_has_files_nonexistent(self) -> None:
        assert FsCompareService._has_files(Path("/nonexistent/path")) is False


class TestFsCompareServiceGetSubdirs:
    """Tests for FsCompareService._get_subdirs."""

    def test_get_subdirs_empty(self, tmp_path: Path) -> None:
        assert FsCompareService._get_subdirs(tmp_path) == []

    def test_get_subdirs_with_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "Season 01").mkdir()
        (tmp_path / "Season 02").mkdir()
        (tmp_path / ".hidden").mkdir()
        result = FsCompareService._get_subdirs(tmp_path)
        assert "Season 01" in result
        assert "Season 02" in result
        assert ".hidden" not in result

    def test_get_subdirs_nonexistent(self) -> None:
        assert FsCompareService._get_subdirs(Path("/nonexistent/path")) == []
