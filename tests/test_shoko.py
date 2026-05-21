"""Tests for Shoko integration models and service."""

from __future__ import annotations

from unittest.mock import MagicMock

from plexctl.models import (
    ShokoEpisodeType,
    ShokoFile,
    ShokoMismatch,
    ShokoSeries,
    ShokoSeriesIDs,
    ShokoSeriesSizes,
    TmdbLinkResult,
    TmdbOrdering,
    TmdbOrderingEpisode,
    TmdbOrderingSeason,
    TmdbSearchResult,
)
from plexctl.plugins.shoko.service import ShokoService


class TestShokoEpisodeType:
    """Test ShokoEpisodeType.from_anidb_type conversion."""

    def test_episode_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(1) == ShokoEpisodeType.EPISODE

    def test_special_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(2) == ShokoEpisodeType.SPECIAL

    def test_credit_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(3) == ShokoEpisodeType.CREDIT

    def test_trailer_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(4) == ShokoEpisodeType.TRAILER

    def test_parody_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(5) == ShokoEpisodeType.PARODY

    def test_other_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(6) == ShokoEpisodeType.OTHER

    def test_unknown_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(0) == ShokoEpisodeType.UNKNOWN

    def test_invalid_type(self) -> None:
        assert ShokoEpisodeType.from_anidb_type(99) == ShokoEpisodeType.UNKNOWN


class TestShokoEpisodeTypeFromString:
    """Test ShokoEpisodeType.from_api_type for string type values."""

    def test_api_type_episode_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("Episode") == ShokoEpisodeType.EPISODE

    def test_api_type_special_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("Special") == ShokoEpisodeType.SPECIAL

    def test_api_type_credit_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("Credit") == ShokoEpisodeType.CREDIT

    def test_api_type_trailer_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("Trailer") == ShokoEpisodeType.TRAILER

    def test_api_type_unknown_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("Unknown") == ShokoEpisodeType.UNKNOWN

    def test_api_type_lowercase_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("episode") == ShokoEpisodeType.EPISODE

    def test_api_type_invalid_string(self) -> None:
        assert ShokoEpisodeType.from_api_type("NonExistent") == ShokoEpisodeType.UNKNOWN

    def test_api_type_int_value(self) -> None:
        """Int values should fall through to from_anidb_type."""
        assert ShokoEpisodeType.from_api_type(1) == ShokoEpisodeType.EPISODE
        assert ShokoEpisodeType.from_api_type(0) == ShokoEpisodeType.UNKNOWN


class TestShokoSeriesIDs:
    """Test ShokoSeriesIDs model."""

    def test_basic_ids(self) -> None:
        ids = ShokoSeriesIDs(id=1, anidb=12345)
        assert ids.id == 1
        assert ids.anidb == 12345
        assert ids.tmdb_show == []
        assert ids.tmdb_movie == []

    def test_ids_with_tmdb(self) -> None:
        ids = ShokoSeriesIDs(id=1, anidb=12345, tmdb_show=[100, 200])
        assert ids.tmdb_show == [100, 200]


class TestShokoSeries:
    """Test ShokoSeries model."""

    def test_basic_series(self) -> None:
        series = ShokoSeries(ids=ShokoSeriesIDs(id=1, anidb=12345), name="Arifureta")
        assert series.name == "Arifureta"
        assert series.episode_count == 0
        assert series.local_sizes.episodes == 0

    def test_series_with_sizes(self) -> None:
        series = ShokoSeries(
            ids=ShokoSeriesIDs(id=1),
            name="One Piece",
            local_sizes=ShokoSeriesSizes(episodes=1000, specials=5),
            total_sizes=ShokoSeriesSizes(episodes=1100, specials=10),
        )
        assert series.local_sizes.episodes == 1000
        assert series.total_sizes.specials == 10


class TestShokoFile:
    """Test ShokoFile model."""

    def test_basic_file(self) -> None:
        f = ShokoFile(id=1, filename="test.mkv")
        assert f.id == 1
        assert f.filename == "test.mkv"
        assert f.is_variation is False
        assert f.is_ignored is False

    def test_file_with_series(self) -> None:
        f = ShokoFile(id=1, series_id=5, series_name="Arifureta")
        assert f.series_id == 5
        assert f.series_name == "Arifureta"


class TestShokoMismatch:
    """Test ShokoMismatch model."""

    def test_no_local_episodes(self) -> None:
        m = ShokoMismatch(
            mismatch_type="no_local_episodes",
            shoko_id=5,
            name="Test Series",
            detail="Series has no local episodes",
            severity="error",
        )
        assert m.mismatch_type == "no_local_episodes"
        assert m.severity == "error"

    def test_no_tmdb_link(self) -> None:
        m = ShokoMismatch(mismatch_type="no_tmdb_link", detail="No TMDB link")
        assert m.severity == "warning"  # default


class TestShokoServiceParseSeries:
    """Test ShokoService._parse_series method."""

    def setup_method(self) -> None:
        mock_client = MagicMock()
        self.service = ShokoService(mock_client)

    def test_parse_series_basic(self) -> None:
        raw = {
            "IDs": {"ID": 1, "AniDB": 12345},
            "Name": "Arifureta",
            "Description": "Test description",
            "Sizes": {
                "Local": {"Episodes": 13, "Specials": 2},
                "Total": {"Episodes": 15, "Specials": 3},
            },
        }
        result = self.service._parse_series(raw)
        assert result.name == "Arifureta"
        assert result.ids.id == 1
        assert result.ids.anidb == 12345
        assert result.local_sizes.episodes == 13
        assert result.total_sizes.specials == 3

    def test_parse_series_with_tmdb(self) -> None:
        raw = {
            "IDs": {"ID": 2, "AniDB": 67890, "TMDB": {"Show": [100, 200], "Movie": [300]}},
            "Name": "Frieren",
            "Sizes": {"Local": {}, "Total": {}},
        }
        result = self.service._parse_series(raw)
        assert result.ids.tmdb_show == [100, 200]
        assert result.ids.tmdb_movie == [300]


class TestShokoServiceParseEpisode:
    """Test ShokoService._parse_episode method."""

    def setup_method(self) -> None:
        mock_client = MagicMock()
        self.service = ShokoService(mock_client)

    def test_parse_episode_basic(self) -> None:
        raw = {
            "ID": 10,
            "Name": "Episode 1",
            "AniDB": {"Type": 1, "EpisodeNumber": 1, "ID": 555},
            "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 1}]},
            "IsHidden": False,
        }
        result = self.service._parse_episode(raw)
        assert result.id == 10
        assert result.name == "Episode 1"
        assert result.episode_type == ShokoEpisodeType.EPISODE
        assert result.episode_number == 1
        assert result.season_number == 1
        assert result.anidb_id == 555

    def test_parse_episode_special(self) -> None:
        raw = {
            "ID": 11,
            "Name": "OVA",
            "AniDB": {"Type": 2, "EpisodeNumber": 1},
            "TMDB": {},
            "IsHidden": False,
        }
        result = self.service._parse_episode(raw)
        assert result.episode_type == ShokoEpisodeType.SPECIAL
        assert result.season_number is None

    def test_parse_episode_no_tmdb(self) -> None:
        raw = {"ID": 12, "Name": "Unknown Ep", "AniDB": {"Type": 0, "EpisodeNumber": 0}}
        result = self.service._parse_episode(raw)
        assert result.episode_type == ShokoEpisodeType.UNKNOWN
        assert result.season_number is None


class TestShokoServiceParseFile:
    """Test ShokoService._parse_file method."""

    def setup_method(self) -> None:
        mock_client = MagicMock()
        self.service = ShokoService(mock_client)

    def test_parse_file_linked_to_series(self) -> None:
        raw = {
            "ID": 100,
            "IsVariation": False,
            "IsIgnored": False,
            "Resolution": "1080p",
            "Duration": 1440000,
            "SeriesIDs": [
                {
                    "SeriesID": {"ID": 5, "Name": "Arifureta"},
                    "EpisodeIDs": [{"ID": 10}, {"ID": 11}],
                }
            ],
            "Locations": [{"RelativePath": "/anime/Arifureta/S01E01.mkv", "IsAccessible": True}],
        }
        result = self.service._parse_file(raw)
        assert result.id == 100
        assert result.series_id == 5
        assert result.series_name == "Arifureta"
        assert result.episode_ids == [10, 11]
        assert result.filename == "S01E01.mkv"
        assert result.is_accessible is True

    def test_parse_file_no_series(self) -> None:
        raw = {
            "ID": 200,
            "IsVariation": True,
            "IsIgnored": False,
            "Resolution": "720p",
            "SeriesIDs": [],
            "Locations": [],
        }
        result = self.service._parse_file(raw)
        assert result.series_id is None
        assert result.is_variation is True
        assert result.resolution == "720p"

    def test_parse_file_with_hashes(self) -> None:
        raw = {
            "ID": 300,
            "IsVariation": False,
            "IsIgnored": False,
            "Resolution": "1080p",
            "SeriesIDs": [{"SeriesID": {"ID": 10, "Name": "Test"}, "EpisodeIDs": []}],
            "Locations": [
                {"RelativePath": "Test/Test_-_01_[ABCDEF12].mkv", "IsAccessible": True}
            ],
            "Hashes": [
                {"Type": "CRC32", "Value": "ABCDEF12"},
                {"Type": "ED2K", "Value": "ed2khash"},
                {"Type": "SHA1", "Value": "sha1hash"},
            ],
        }
        result = self.service._parse_file(raw)
        assert result.crc32 == "ABCDEF12"
        assert result.ed2k == "ed2khash"
        assert result.sha1 == "sha1hash"

    def test_parse_file_with_placeholder_no_crc(self) -> None:
        raw = {
            "ID": 400,
            "IsVariation": False,
            "IsIgnored": False,
            "Resolution": "1080p",
            "SeriesIDs": [{"SeriesID": {"ID": 20, "Name": "One Piece"}, "EpisodeIDs": []}],
            "Locations": [
                {"RelativePath": "One_Piece/One_Piece_-_001_[%CRC].mkv", "IsAccessible": True}
            ],
            "Hashes": [
                {"Type": "SHA1", "Value": "sha1hash"},
                {"Type": "ED2K", "Value": "ed2khash"},
            ],
        }
        result = self.service._parse_file(raw)
        assert result.crc32 is None
        assert result.ed2k == "ed2khash"
        assert result.sha1 == "sha1hash"


class TestShokoServiceParseGroup:
    """Test ShokoService._parse_group method."""

    def setup_method(self) -> None:
        mock_client = MagicMock()
        self.service = ShokoService(mock_client)

    def test_parse_group(self) -> None:
        raw = {
            "IDs": {"ID": 50, "SeriesIDs": [1, 2, 3]},
            "Name": "Arifureta franchise",
            "Sizes": {"Series": 3},
        }
        result = self.service._parse_group(raw)
        assert result.id == 50
        assert result.name == "Arifureta franchise"
        assert result.series_count == 3
        assert result.series_ids == [1, 2, 3]


class TestTmdbSearchResult:
    """Test TmdbSearchResult model."""

    def test_basic_search_result(self) -> None:
        result = TmdbSearchResult(
            id=37854, name="One Piece", overview="A pirate adventure anime", year=1999
        )
        assert result.id == 37854
        assert result.name == "One Piece"
        assert result.year == 1999

    def test_minimal_search_result(self) -> None:
        result = TmdbSearchResult(id=123, name="Test Show")
        assert result.overview is None
        assert result.year is None
        assert result.first_aired is None
        assert result.poster_url is None


class TestTmdbLinkResult:
    """Test TmdbLinkResult model."""

    def test_successful_link(self) -> None:
        result = TmdbLinkResult(series_id=1, tmdb_id=123, action="linked", success=True)
        assert result.success is True
        assert result.error is None

    def test_failed_link(self) -> None:
        result = TmdbLinkResult(
            series_id=1, tmdb_id=123, action="linked", success=False, error="Not found"
        )
        assert result.success is False
        assert result.error == "Not found"


class TestShokoServiceTmdbSearch:
    """Test ShokoService.search_tmdb_shows and search_tmdb_movies."""

    def setup_method(self) -> None:
        self.mock_client = MagicMock()
        self.service = ShokoService(self.mock_client)

    def test_search_tmdb_shows(self) -> None:
        self.mock_client.get_list.return_value = (
            [
                {
                    "ID": 37854,
                    "Title": "One Piece",
                    "Overview": "A pirate adventure",
                    "FirstAiredAt": "1999-10-20",
                },
                {
                    "ID": 31911,
                    "Title": "Naruto",
                    "Overview": "A ninja story",
                    "FirstAiredAt": "2002-10-03",
                },
            ],
            2,
        )
        results = self.service.search_tmdb_shows("One Piece")
        assert len(results) == 2
        assert results[0].id == 37854
        assert results[0].name == "One Piece"
        assert results[0].year == 1999
        self.mock_client.get_list.assert_called_once_with(
            "/Tmdb/Show/Online/Search", {"query": "One Piece"}
        )

    def test_search_tmdb_shows_with_year(self) -> None:
        self.mock_client.get_list.return_value = ([], 0)
        self.service.search_tmdb_shows("test", year=2024)
        self.mock_client.get_list.assert_called_once_with(
            "/Tmdb/Show/Online/Search", {"query": "test", "year": 2024}
        )

    def test_search_tmdb_movies(self) -> None:
        self.mock_client.get_list.return_value = (
            [{"ID": 123, "Title": "Spirited Away", "ReleasedAt": "2001-07-20"}],
            1,
        )
        results = self.service.search_tmdb_movies("Spirited Away")
        assert len(results) == 1
        assert results[0].id == 123
        assert results[0].year == 2001
        self.mock_client.get_list.assert_called_once_with(
            "/Tmdb/Movie/Online/Search", {"query": "Spirited Away"}
        )


class TestShokoServiceTmdbLink:
    """Test ShokoService TMDB link/unlink/refresh methods."""

    def setup_method(self) -> None:
        self.mock_client = MagicMock()
        self.service = ShokoService(self.mock_client)

    def test_link_tmdb_show_success(self) -> None:
        self.mock_client.post.return_value = None  # 204 No Content
        result = self.service.link_tmdb_show(1, 123)
        assert result.success is True
        assert result.series_id == 1
        assert result.tmdb_id == 123
        assert result.action == "linked"
        self.mock_client.post.assert_called_once_with(
            "/Series/1/TMDB/Show", json={"ID": 123, "Replace": False, "Refresh": False}
        )

    def test_link_tmdb_show_with_replace(self) -> None:
        self.mock_client.post.return_value = None
        result = self.service.link_tmdb_show(1, 456, replace=True, refresh=False)
        assert result.success is True
        self.mock_client.post.assert_called_once_with(
            "/Series/1/TMDB/Show", json={"ID": 456, "Replace": True, "Refresh": False}
        )

    def test_link_tmdb_show_failure(self) -> None:
        self.mock_client.post.side_effect = Exception("Not found")
        result = self.service.link_tmdb_show(1, 999)
        assert result.success is False
        assert result.error == "Not found"

    def test_link_tmdb_movie_success(self) -> None:
        self.mock_client.post.return_value = None
        result = self.service.link_tmdb_movie(218, 683127, anidb_episode_id=229573)
        assert result.success is True
        assert result.series_id == 218
        assert result.tmdb_id == 683127
        assert result.action == "linked"
        self.mock_client.post.assert_called_once_with(
            "/Series/218/TMDB/Movie",
            json={"ID": 683127, "EpisodeID": 229573, "Replace": False, "Refresh": False},
        )

    def test_unlink_tmdb_show_success(self) -> None:
        self.mock_client.delete.return_value = None
        result = self.service.unlink_tmdb_show(1, 123)
        assert result.success is True
        assert result.action == "unlinked"
        self.mock_client.delete.assert_called_once_with(
            "/Series/1/TMDB/Show", json={"ID": 123, "Purge": False}
        )

    def test_unlink_tmdb_show_with_purge(self) -> None:
        self.mock_client.delete.return_value = None
        result = self.service.unlink_tmdb_show(1, 123, purge=True)
        assert result.success is True
        self.mock_client.delete.assert_called_once_with(
            "/Series/1/TMDB/Show", json={"ID": 123, "Purge": True}
        )

    def test_unlink_tmdb_show_failure(self) -> None:
        self.mock_client.delete.side_effect = Exception("Forbidden")
        result = self.service.unlink_tmdb_show(1, 123)
        assert result.success is False
        assert result.error == "Forbidden"

    def test_refresh_tmdb_show_success(self) -> None:
        self.mock_client.post.return_value = None
        result = self.service.refresh_tmdb_show(1)
        assert result.success is True
        assert result.action == "refreshed"
        self.mock_client.post.assert_called_once_with(
            "/Series/1/TMDB/Show/Action/Refresh",
            json={"Immediate": True, "Force": True, "DownloadImages": True},
        )

    def test_refresh_tmdb_show_failure(self) -> None:
        self.mock_client.post.side_effect = Exception("Server error")
        result = self.service.refresh_tmdb_show(1)
        assert result.success is False
        assert result.error == "Server error"


class TestCrcAuditModels:
    """Test CRC audit models."""

    def test_crc_audit_result_defaults(self) -> None:
        from plexctl.models import CrcAuditResult

        result = CrcAuditResult(series_id=1, series_name="Test")
        assert result.total_files == 0
        assert result.files_with_crc == 0
        assert result.files_missing_crc == 0
        assert result.files_no_bracket == 0
        assert result.missing_crc_paths == []

    def test_crc_audit_result_with_data(self) -> None:
        from plexctl.models import CrcAuditResult

        result = CrcAuditResult(
            series_id=42,
            series_name="One Piece",
            total_files=1194,
            files_with_crc=0,
            files_missing_crc=1194,
            files_no_bracket=0,
            missing_crc_paths=["One_Piece/One_Piece_-_001_[%CRC].mkv"],
        )
        assert result.files_missing_crc == 1194
        assert len(result.missing_crc_paths) == 1

    def test_crc_audit_report_defaults(self) -> None:
        from plexctl.models import CrcAuditReport

        report = CrcAuditReport()
        assert report.total_series == 0
        assert report.total_files == 0
        assert report.series_missing_crc == []

    def test_shoko_file_hash_fields(self) -> None:
        from plexctl.models import ShokoFile

        f = ShokoFile(
            id=1, filename="test.mkv", crc32="ABCDEF12", ed2k="ed2khash", sha1="sha1hash"
        )
        assert f.crc32 == "ABCDEF12"
        assert f.ed2k == "ed2khash"
        assert f.sha1 == "sha1hash"

    def test_shoko_file_hash_defaults(self) -> None:
        from plexctl.models import ShokoFile

        f = ShokoFile(id=1)
        assert f.crc32 is None
        assert f.ed2k is None
        assert f.sha1 is None


class TestCrcAuditService:
    """Test CRC audit service methods."""

    def test_audit_crc_hashes_with_placeholder(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        # Mock file with %CRC placeholder
        mock_client.get_list.return_value = (
            [
                {
                    "ID": 1,
                    "SeriesIDs": [
                        {"SeriesID": {"ID": 10, "Name": "One Piece"}, "EpisodeIDs": []}
                    ],
                    "Locations": [
                        {
                            "RelativePath": "One_Piece/One_Piece_-_001_[%CRC].mkv",
                            "IsAccessible": True,
                        }
                    ],
                    "Hashes": [
                        {"Type": "SHA1", "Value": "abc123"},
                        {"Type": "ED2K", "Value": "def456"},
                    ],
                    "IsVariation": False,
                    "IsIgnored": False,
                },
                {
                    "ID": 2,
                    "SeriesIDs": [
                        {"SeriesID": {"ID": 20, "Name": "Black Clover"}, "EpisodeIDs": []}
                    ],
                    "Locations": [
                        {
                            "RelativePath": ("Black_Clover/Black_Clover_-_001_[350F23E7].mkv"),
                            "IsAccessible": True,
                        }
                    ],
                    "Hashes": [
                        {"Type": "CRC32", "Value": "350F23E7"},
                        {"Type": "SHA1", "Value": "sha1hash"},
                        {"Type": "ED2K", "Value": "ed2khash"},
                    ],
                    "IsVariation": False,
                    "IsIgnored": False,
                },
            ],
            2,
        )

        _, report = service.audit_crc_hashes()

        assert report.total_files == 2
        assert report.files_with_crc == 1
        assert report.files_missing_crc == 1
        assert len(report.series_missing_crc) == 1
        assert report.series_missing_crc[0].series_name == "One Piece"
        assert report.series_missing_crc[0].files_missing_crc == 1

    def test_audit_crc_hashes_all_real(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get_list.return_value = (
            [
                {
                    "ID": 1,
                    "SeriesIDs": [{"SeriesID": {"ID": 10, "Name": "Test"}, "EpisodeIDs": []}],
                    "Locations": [
                        {"RelativePath": "Test/Test_-_01_[ABCDEF12].mkv", "IsAccessible": True}
                    ],
                    "Hashes": [{"Type": "CRC32", "Value": "ABCDEF12"}],
                    "IsVariation": False,
                    "IsIgnored": False,
                }
            ],
            1,
        )

        _, report = service.audit_crc_hashes()

        assert report.files_with_crc == 1
        assert report.files_missing_crc == 0
        assert report.series_missing_crc == []

    def test_rehash_file_success(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.post.return_value = None
        result = service.rehash_file(123)
        assert result is True
        mock_client.post.assert_called_once_with("/File/123/Rehash")

    def test_rehash_file_failure(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.post.side_effect = Exception("Error")
        result = service.rehash_file(123)
        assert result is False

    def test_rescan_file_success(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.post.return_value = None
        result = service.rescan_file(123)
        assert result is True
        mock_client.post.assert_called_once_with("/File/123/Rescan")

    def test_trigger_import_success(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.return_value = {}
        result = service.trigger_import()
        assert result is True
        mock_client.get.assert_called_once_with("/Action/ImportNewFiles")

    def test_trigger_update_media_info_success(self) -> None:
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.return_value = {}
        result = service.trigger_update_media_info()
        assert result is True
        mock_client.get.assert_called_once_with("/Action/UpdateAllMediaInfo")


class TestBatchRehashMissingCrc:
    """Test batch_rehash_missing_crc service method."""

    def _make_file_data(self, file_id: int, path: str, crc32_hash: str | None = None) -> dict:
        """Build a mock file API response dict."""
        hashes = [{"Type": "ED2K", "Value": "ed2khash"}, {"Type": "SHA1", "Value": "sha1hash"}]
        if crc32_hash:
            hashes.append({"Type": "CRC32", "Value": crc32_hash})
        return {
            "ID": file_id,
            "SeriesIDs": [{"SeriesID": {"ID": 1, "Name": "Test"}, "EpisodeIDs": []}],
            "Locations": [{"RelativePath": path, "IsAccessible": True}],
            "Hashes": hashes,
            "IsVariation": False,
            "IsIgnored": False,
        }

    def test_batch_rehash_skips_files_with_crc(self) -> None:
        """Files that already have CRC in name AND hash should be skipped."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get_list.return_value = (
            [self._make_file_data(1, "Test/Ep01_[ABCDEF12].mkv", "ABCDEF12")],
            1,
        )
        mock_client.post.return_value = None

        result = service.batch_rehash_missing_crc()

        assert result.total == 0
        assert result.succeeded == 0
        mock_client.post.assert_not_called()

    def test_batch_rehash_triggers_for_placeholder_files(self) -> None:
        """Files with %CRC placeholder should be rehashed."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get_list.return_value = ([self._make_file_data(1, "Test/Ep01_[%CRC].mkv")], 1)
        mock_client.post.return_value = None

        result = service.batch_rehash_missing_crc()

        assert result.total == 1
        assert result.succeeded == 1
        assert result.failed == 0
        mock_client.post.assert_called_once_with("/File/1/Rehash")

    def test_batch_rehash_triggers_for_missing_hash(self) -> None:
        """Files with CRC in name but no CRC32 hash should be rehashed."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get_list.return_value = (
            [self._make_file_data(1, "Test/Ep01_[ABCDEF12].mkv", None)],
            1,
        )
        mock_client.post.return_value = None

        result = service.batch_rehash_missing_crc()

        assert result.total == 1
        assert result.succeeded == 1

    def test_batch_rehash_reports_failures(self) -> None:
        """Failed rehashes should be counted in result."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get_list.return_value = ([self._make_file_data(1, "Test/Ep01_[%CRC].mkv")], 1)
        mock_client.post.side_effect = Exception("error")

        result = service.batch_rehash_missing_crc()

        assert result.total == 1
        assert result.succeeded == 0
        assert result.failed == 1


class TestPlexMatchModels:
    """Test PlexMatch and PlexMatchEntry models."""

    def test_plexmatch_entry_basic(self) -> None:
        from plexctl.models import PlexMatchEntry

        entry = PlexMatchEntry(season_number=1, episode_number=1, filename="Episode_01.mkv")
        assert entry.season_number == 1
        assert entry.episode_number == 1
        assert entry.filename == "Episode_01.mkv"

    def test_plexmatch_render_minimal(self) -> None:
        from plexctl.models import PlexMatch

        pm = PlexMatch(title="Test Series")
        content = pm.render()
        assert content == "Title: Test Series"

    def test_plexmatch_render_with_year(self) -> None:
        from plexctl.models import PlexMatch

        pm = PlexMatch(title="Test Series", year=2025)
        content = pm.render()
        assert "Title: Test Series" in content
        assert "Year: 2025" in content

    def test_plexmatch_render_with_ids(self) -> None:
        from plexctl.models import PlexMatch

        pm = PlexMatch(title="WITCH WATCH", year=2025, tvdb_id=453127, imdb_id="tt33165027")
        content = pm.render()
        assert "Title: WITCH WATCH" in content
        assert "Year: 2025" in content
        assert "TvdbId: 453127" in content
        assert "ImdbId: tt33165027" in content

    def test_plexmatch_render_with_entries(self) -> None:
        from plexctl.models import PlexMatch, PlexMatchEntry

        entries = [
            PlexMatchEntry(
                season_number=1,
                episode_number=1,
                filename="Witch_Watch_-_01_(1080p)_[F15DB9CE].mkv",
            ),
            PlexMatchEntry(
                season_number=1,
                episode_number=2,
                filename="Witch_Watch_-_02_(1080p)_[788CDEAC].mkv",
            ),
        ]
        pm = PlexMatch(
            title="WITCH WATCH", year=2025, tvdb_id=453127, imdb_id="tt33165027", entries=entries
        )
        content = pm.render()
        assert "Title: WITCH WATCH" in content
        assert "Year: 2025" in content
        assert "TvdbId: 453127" in content
        assert "ImdbId: tt33165027" in content
        assert "Episode: S01E01: Witch_Watch_-_01_(1080p)_[F15DB9CE].mkv" in content
        assert "Episode: S01E02: Witch_Watch_-_02_(1080p)_[788CDEAC].mkv" in content

    def test_plexmatch_render_skips_none_fields(self) -> None:
        from plexctl.models import PlexMatch

        pm = PlexMatch(title="Test Series")
        content = pm.render()
        assert "Year:" not in content
        assert "TvdbId:" not in content
        assert "ImdbId:" not in content
        assert "TmdbId:" not in content

    def test_plexmatch_entry_with_relative_path(self) -> None:
        """Episode filenames can contain relative paths for season subdirs."""
        from plexctl.models import PlexMatch, PlexMatchEntry

        entries = [
            PlexMatchEntry(
                season_number=1, episode_number=1, filename="Season 01/Episode_01.mkv"
            ),
            PlexMatchEntry(
                season_number=0, episode_number=1, filename="Season 00/Special_01.mkv"
            ),
        ]
        pm = PlexMatch(title="Relative Path Series", year=2024, entries=entries)
        content = pm.render()
        assert "Episode: S01E01: Season 01/Episode_01.mkv" in content
        assert "Episode: S00E01: Season 00/Special_01.mkv" in content


class TestPlexMatchGeneration:
    """Test ShokoService.generate_plexmatch method."""

    def _make_series_response(self, series_id: int = 1) -> dict:
        """Build a mock series API response."""
        return {
            "IDs": {
                "ID": series_id,
                "AniDB": 12345,
                "TMDB": {"Show": [100], "Movie": []},
                "TvDB": [453127],
                "IMDB": ["tt33165027"],
            },
            "Name": "WITCH WATCH",
            "Sizes": {"Local": {"Episodes": 25}, "Total": {"Episodes": 25}},
        }

    def _make_episode_response(
        self,
        episode_id: int,
        episode_number: int,
        season_number: int = 1,
        episode_type: str = "Episode",
        is_hidden: bool = False,
    ) -> dict:
        """Build a mock episode API response."""
        return {
            "ID": episode_id,
            "Name": f"Episode {episode_number}",
            "AniDB": {
                "Type": episode_type,
                "EpisodeNumber": episode_number,
                "ID": episode_id * 100,
            },
            "TMDB": {
                "Episodes": [{"SeasonNumber": season_number, "EpisodeNumber": episode_number}]
            },
            "IsHidden": is_hidden,
        }

    def _make_file_response(
        self,
        file_id: int,
        series_id: int,
        episode_ids: list[int],
        filename: str,
        relative_path: str | None = None,
    ) -> dict:
        """Build a mock file API response.

        Args:
            file_id: Shoko file ID.
            series_id: Shoko series ID.
            episode_ids: Episode IDs linked to this file.
            filename: Bare filename (e.g. "Ep01.mkv").
            relative_path: Full path relative to managed folder root.
                Defaults to "WITCH WATCH/{filename}" if not provided.
        """
        if relative_path is None:
            relative_path = f"WITCH WATCH/{filename}"
        return {
            "ID": file_id,
            "IsVariation": False,
            "IsIgnored": False,
            "Resolution": "1080p",
            "SeriesIDs": [
                {
                    "SeriesID": {"ID": series_id, "Name": "WITCH WATCH"},
                    "EpisodeIDs": [{"ID": eid} for eid in episode_ids],
                }
            ],
            "Locations": [{"RelativePath": relative_path, "IsAccessible": True}],
            "Hashes": [],
        }

    def test_generate_plexmatch_basic(self) -> None:
        """Test basic plexmatch generation with series data."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        # Mock series detail
        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # Mock episodes
        mock_client.get_list.side_effect = lambda path, params=None: (
            [
                self._make_episode_response(1, 1, season_number=1),
                self._make_episode_response(2, 2, season_number=1),
            ],
            2,
        )

        result = service.generate_plexmatch(1)

        assert result.title == "WITCH WATCH"
        assert result.year == 2025
        assert result.tvdb_id == 453127
        assert result.imdb_id == "tt33165027"
        assert result.tmdb_id == 100

    def test_generate_plexmatch_no_year(self) -> None:
        """Test plexmatch generation when AniDB year is unavailable."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {},
        }.get(path, {})

        mock_client.get_list.side_effect = lambda path, params=None: ([], 0)

        result = service.generate_plexmatch(1)

        assert result.year is None

    def test_generate_plexmatch_no_external_ids(self) -> None:
        """Test plexmatch when series has no TVDB/IMDB IDs."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        series_no_ids = {
            "IDs": {
                "ID": 2,
                "AniDB": 99999,
                "TMDB": {"Show": [], "Movie": []},
                "TvDB": [],
                "IMDB": [],
            },
            "Name": "Unknown Series",
            "Sizes": {"Local": {"Episodes": 10}, "Total": {"Episodes": 10}},
        }

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/2": series_no_ids,
            "/Series/2/AniDB": {"AirDate": "2023-01-01"},
        }.get(path, {})

        mock_client.get_list.side_effect = lambda path, params=None: ([], 0)

        result = service.generate_plexmatch(2)

        assert result.title == "Unknown Series"
        assert result.tvdb_id is None
        assert result.imdb_id is None
        assert result.tmdb_id is None

    def test_generate_plexmatch_with_entries(self) -> None:
        """Test plexmatch generation with episode-to-file mappings."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # Episodes: 3 regular, 2 specials with files, 1 hidden (excluded)
        episodes = [
            self._make_episode_response(1, 1, season_number=1),
            self._make_episode_response(2, 2, season_number=1),
            self._make_episode_response(3, 3, season_number=1),
            self._make_episode_response(
                10, 1, season_number=0, episode_type="Special"
            ),  # special S00E01
            self._make_episode_response(
                11, 2, season_number=0, episode_type="Special"
            ),  # special S00E02
            self._make_episode_response(
                99, 99, season_number=1, is_hidden=True
            ),  # hidden - excluded
        ]

        # Files: 3 regular + 2 specials = 5 files
        files = [
            self._make_file_response(1, 1, [1], "Witch_Watch_-_01_[F15DB9CE].mkv"),
            self._make_file_response(2, 1, [2], "Witch_Watch_-_02_[788CDEAC].mkv"),
            self._make_file_response(3, 1, [3], "Witch_Watch_-_03_[7CAB7613].mkv"),
            self._make_file_response(4, 1, [10], "Witch_Watch_SP01_[AA111111].mkv"),
            self._make_file_response(5, 1, [11], "Witch_Watch_SP02_[BB222222].mkv"),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 6
            elif "/Series/1/File" in path:
                return files, 5
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1)

        # 3 regular + 2 specials = 5, hidden excluded
        assert len(result.entries) == 5

        # Entries sorted by (season_number, episode_number)
        # Season 0 specials come first, then season 1
        assert result.entries[0].season_number == 0  # special
        assert result.entries[0].episode_number == 1  # special ep 1
        assert result.entries[0].filename == "Witch_Watch_SP01_[AA111111].mkv"

        # Index 2 = S01E01 (first regular after 2 specials)
        assert result.entries[2].season_number == 1  # regular
        assert result.entries[2].episode_number == 1

    def test_generate_plexmatch_no_episodes(self) -> None:
        """Test plexmatch generation for series with no episodes."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        mock_client.get_list.side_effect = lambda path, params=None: ([], 0)

        result = service.generate_plexmatch(1)

        assert result.title == "WITCH WATCH"
        assert len(result.entries) == 0

    def test_plexmatch_render_full(self) -> None:
        """Test full render of a plexmatch file."""
        from plexctl.models import PlexMatch, PlexMatchEntry

        entries = [
            PlexMatchEntry(
                season_number=1, episode_number=1, filename="Show_-_01_[ABC12345].mkv"
            ),
            PlexMatchEntry(
                season_number=1, episode_number=2, filename="Show_-_02_[DEF67890].mkv"
            ),
        ]

        pm = PlexMatch(
            title="WITCH WATCH", year=2025, tvdb_id=453127, imdb_id="tt33165027", entries=entries
        )

        content = pm.render()
        lines = content.split("\n")

        assert lines[0] == "Title: WITCH WATCH"
        assert lines[1] == "Year: 2025"
        assert lines[2] == "TvdbId: 453127"
        assert lines[3] == "ImdbId: tt33165027"
        assert lines[4] == "Episode: S01E01: Show_-_01_[ABC12345].mkv"
        assert lines[5] == "Episode: S01E02: Show_-_02_[DEF67890].mkv"

    def test_generate_plexmatch_filters_variations_and_ignored(self) -> None:
        """Test that variation and ignored files are excluded."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [self._make_episode_response(1, 1, season_number=1)]

        files = [
            # Normal file - should be included
            {
                "ID": 1,
                "IsVariation": False,
                "IsIgnored": False,
                "Resolution": "1080p",
                "SeriesIDs": [
                    {"SeriesID": {"ID": 1, "Name": "WITCH WATCH"}, "EpisodeIDs": [{"ID": 1}]}
                ],
                "Locations": [{"RelativePath": "WITCH WATCH/Ep01.mkv", "IsAccessible": True}],
                "Hashes": [],
            },
            # Variation file - should be excluded
            {
                "ID": 2,
                "IsVariation": True,
                "IsIgnored": False,
                "Resolution": "720p",
                "SeriesIDs": [
                    {"SeriesID": {"ID": 1, "Name": "WITCH WATCH"}, "EpisodeIDs": [{"ID": 1}]}
                ],
                "Locations": [{"RelativePath": "WITCH WATCH/Ep01_720.mkv", "IsAccessible": True}],
                "Hashes": [],
            },
            # Ignored file - should be excluded
            {
                "ID": 3,
                "IsVariation": False,
                "IsIgnored": True,
                "Resolution": "1080p",
                "SeriesIDs": [
                    {"SeriesID": {"ID": 1, "Name": "WITCH WATCH"}, "EpisodeIDs": [{"ID": 1}]}
                ],
                "Locations": [{"RelativePath": "WITCH WATCH/Ep01_alt.mkv", "IsAccessible": True}],
                "Hashes": [],
            },
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 1
            elif "/File" in path:
                return files, 3
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1)

        # Only the non-variation, non-ignored file should appear
        assert len(result.entries) == 1
        assert result.entries[0].filename == "Ep01.mkv"

    def test_generate_plexmatch_deduplication(self) -> None:
        """Test that duplicate season/episode entries are deduplicated."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # Two Shoko episodes mapping to S01E01 (e.g. regular + alt version)
        episodes = [
            self._make_episode_response(1, 1, season_number=1),
            self._make_episode_response(2, 1, season_number=1),  # same season/ep
        ]

        # Each episode has its own file
        files = [
            self._make_file_response(1, 1, [1], "Ep01_version1.mkv"),
            self._make_file_response(2, 1, [2], "Ep01_version2.mkv"),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 2
            elif "/File" in path:
                return files, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1)

        # Only one entry for S01E01 (first file wins)
        assert len(result.entries) == 1
        assert result.entries[0].filename == "Ep01_version1.mkv"

    def test_plexmatch_dir_strips_series_prefix(self) -> None:
        """When plexmatch_dir is provided, paths are relative to that dir."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [
            self._make_episode_response(1, 1, season_number=1),
            self._make_episode_response(2, 2, season_number=1),
        ]
        files = [
            # File in a Season 01 subdirectory
            self._make_file_response(
                1,
                1,
                [1],
                "Witch_Watch_-_01_[F15DB9CE].mkv",
                relative_path="WITCH WATCH/Season 01/Witch_Watch_-_01_[F15DB9CE].mkv",
            ),
            # File directly in the series directory
            self._make_file_response(
                2,
                1,
                [2],
                "Witch_Watch_-_02_[788CDEAC].mkv",
                relative_path="WITCH WATCH/Witch_Watch_-_02_[788CDEAC].mkv",
            ),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 2
            elif "/File" in path:
                return files, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1, plexmatch_dir="WITCH WATCH")

        # File in season subdir should have relative path preserved
        assert result.entries[0].filename == "Season 01/Witch_Watch_-_01_[F15DB9CE].mkv"
        # File directly in series dir should have bare filename
        assert result.entries[1].filename == "Witch_Watch_-_02_[788CDEAC].mkv"

    def test_plexmatch_dir_none_uses_bare_filename(self) -> None:
        """Without plexmatch_dir, bare filenames are used (backward compat)."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [self._make_episode_response(1, 1, season_number=1)]
        files = [
            # File in a Season 01 subdirectory (has relative_path with subdir)
            self._make_file_response(
                1,
                1,
                [1],
                "Witch_Watch_-_01_[F15DB9CE].mkv",
                relative_path="WITCH WATCH/Season 01/Witch_Watch_-_01_[F15DB9CE].mkv",
            )
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 1
            elif "/File" in path:
                return files, 1
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        # Without plexmatch_dir, should use bare filename
        result = service.generate_plexmatch(1)

        assert result.entries[0].filename == "Witch_Watch_-_01_[F15DB9CE].mkv"

    def test_plexmatch_dir_nonmatching_prefix_falls_back(self) -> None:
        """If relative_path doesn't start with plexmatch_dir, fall back to filename."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [self._make_episode_response(1, 1, season_number=1)]
        # relative_path starts with different prefix than plexmatch_dir
        files = [
            self._make_file_response(
                1, 1, [1], "Ep01.mkv", relative_path="Different Show Name/Ep01.mkv"
            )
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 1
            elif "/File" in path:
                return files, 1
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        # plexmatch_dir doesn't match the relative_path prefix
        result = service.generate_plexmatch(1, plexmatch_dir="WITCH WATCH")

        # Should fall back to bare filename when prefix doesn't match
        assert result.entries[0].filename == "Ep01.mkv"

    def test_plexmatch_dir_specials_with_season_path(self) -> None:
        """Specials in a Season 00 subdirectory get correct relative paths."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [
            self._make_episode_response(10, 1, season_number=0, episode_type="Special"),
            self._make_episode_response(11, 2, season_number=0, episode_type="Special"),
            self._make_episode_response(1, 1, season_number=1),
        ]
        files = [
            self._make_file_response(
                4,
                1,
                [10],
                "Witch_Watch_SP01_[AA].mkv",
                relative_path="WITCH WATCH/Season 00/Witch_Watch_SP01_[AA].mkv",
            ),
            self._make_file_response(
                5,
                1,
                [11],
                "Witch_Watch_SP02_[BB].mkv",
                relative_path="WITCH WATCH/Season 00/Witch_Watch_SP02_[BB].mkv",
            ),
            self._make_file_response(
                1,
                1,
                [1],
                "Witch_Watch_-_01_[F15DB9CE].mkv",
                relative_path="WITCH WATCH/Season 01/Witch_Watch_-_01_[F15DB9CE].mkv",
            ),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 3
            elif "/File" in path:
                return files, 3
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1, plexmatch_dir="WITCH WATCH")

        assert result.entries[0].season_number == 0
        assert result.entries[0].filename == "Season 00/Witch_Watch_SP01_[AA].mkv"
        assert result.entries[1].filename == "Season 00/Witch_Watch_SP02_[BB].mkv"
        assert result.entries[2].filename == "Season 01/Witch_Watch_-_01_[F15DB9CE].mkv"

    def test_plexmatch_no_tmdb_mapping_defaults_to_s00(self) -> None:
        """Episodes with no TMDB season/episode mapping default to S00.

        Handles cases like OVAs that Shoko classifies as "Episode" type
        but which have no TMDB mapping. These belong in S00, not S01.
        """
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # An OVA episode: type=Episode, tmdb_episode_number=None, season_number=None
        ova_episode = {
            "ID": 50,
            "Name": "Welcome to Fairy Hills!!",
            "AniDB": {"Type": "Episode", "EpisodeNumber": 1, "ID": 5000},
            # No TMDB data at all
            "TMDB": {"Episodes": []},
            "IsHidden": False,
        }
        regular_episode = self._make_episode_response(1, 1, season_number=1)

        episodes = [ova_episode, regular_episode]
        files = [
            self._make_file_response(
                10,
                1,
                [50],
                "OVA_Special_[ABC].mkv",
                relative_path="WITCH WATCH/OVA_Special_[ABC].mkv",
            ),
            self._make_file_response(
                1,
                1,
                [1],
                "Witch_Watch_-_01_[F15DB9CE].mkv",
                relative_path="WITCH WATCH/Season 01/Witch_Watch_-_01_[F15DB9CE].mkv",
            ),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 2
            elif "/File" in path:
                return files, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        result = service.generate_plexmatch(1, plexmatch_dir="WITCH WATCH")

        # OVA with no TMDB data should go to S00, not S01
        assert result.entries[0].season_number == 0
        assert result.entries[0].episode_number == 1
        # Regular episode with TMDB season should go to S01
        assert result.entries[1].season_number == 1

    def test_plexmatch_with_ordering_remaps_season(self) -> None:
        """Ordering episode map remaps TMDB episode IDs to different seasons.

        Simulates One Piece where the default ordering puts eps in S01,
        but the TVDB Order puts them into different seasons (e.g. S02).
        """
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # Three episodes with TMDB episode IDs: 852692, 852693, 852694
        # Default: all in S01. TVDB Order: ep1 in S01, ep2/3 in S02.
        episodes = [
            {
                "ID": 1,
                "Name": "Episode 1",
                "AniDB": {"Type": "Episode", "EpisodeNumber": 1, "ID": 100},
                "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 1, "ID": 852692}]},
                "IsHidden": False,
            },
            {
                "ID": 2,
                "Name": "Episode 2",
                "AniDB": {"Type": "Episode", "EpisodeNumber": 2, "ID": 200},
                "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 2, "ID": 852693}]},
                "IsHidden": False,
            },
            {
                "ID": 3,
                "Name": "Episode 3",
                "AniDB": {"Type": "Episode", "EpisodeNumber": 3, "ID": 300},
                "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 3, "ID": 852694}]},
                "IsHidden": False,
            },
        ]

        files = [
            self._make_file_response(1, 1, [1], "Ep01.mkv"),
            self._make_file_response(2, 1, [2], "Ep02.mkv"),
            self._make_file_response(3, 1, [3], "Ep03.mkv"),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 3
            elif "/File" in path:
                return files, 3
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        # TVDB Order: ep 852692 → S01E01, ep 852693 → S02E01, ep 852694 → S02E02
        ordering_map = {852692: (1, 1), 852693: (2, 1), 852694: (2, 2)}

        entries = service._build_plexmatch_entries(1, ordering_episode_map=ordering_map)

        assert len(entries) == 3
        # Ep1 → S01E01 (same as default)
        assert entries[0].season_number == 1
        assert entries[0].episode_number == 1
        # Ep2 → S02E01 (remapped from S01)
        assert entries[1].season_number == 2
        assert entries[1].episode_number == 1
        # Ep3 → S02E02 (remapped from S01)
        assert entries[2].season_number == 2
        assert entries[2].episode_number == 2

    def test_plexmatch_ordering_unmapped_episode_falls_back(self) -> None:
        """Episodes not in the ordering map fall back to Shoko's stored data."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        # Episode 1 has TMDB ID in map; Episode 2 does NOT
        episodes = [
            {
                "ID": 1,
                "Name": "Episode 1",
                "AniDB": {"Type": "Episode", "EpisodeNumber": 1, "ID": 100},
                "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 1, "ID": 852692}]},
                "IsHidden": False,
            },
            {
                "ID": 2,
                "Name": "Episode 2",
                "AniDB": {"Type": "Episode", "EpisodeNumber": 2, "ID": 200},
                "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 2, "ID": 999999}]},
                "IsHidden": False,
            },
        ]

        files = [
            self._make_file_response(1, 1, [1], "Ep01.mkv"),
            self._make_file_response(2, 1, [2], "Ep02.mkv"),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 2
            elif "/File" in path:
                return files, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        # Only ep 852692 is in the ordering; 999999 is not
        ordering_map = {852692: (2, 1)}  # remap S01E01 → S02E01

        entries = service._build_plexmatch_entries(1, ordering_episode_map=ordering_map)

        assert len(entries) == 2
        # Ep2 → S01E02 (fallback: not in ordering map, uses Shoko stored data)
        assert entries[0].season_number == 1
        assert entries[0].episode_number == 2
        # Ep1 → S02E01 (from ordering map)
        assert entries[1].season_number == 2
        assert entries[1].episode_number == 1

    def test_plexmatch_ordering_with_none_map_uses_default(self) -> None:
        """When ordering_episode_map is None, behavior is unchanged."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        mock_client.get.side_effect = lambda path, params=None: {
            "/Series/1": self._make_series_response(1),
            "/Series/1/AniDB": {"AirDate": "2025-04-06"},
        }.get(path, {})

        episodes = [
            self._make_episode_response(1, 1, season_number=1),
            self._make_episode_response(2, 2, season_number=1),
        ]
        files = [
            self._make_file_response(1, 1, [1], "Ep01.mkv"),
            self._make_file_response(2, 1, [2], "Ep02.mkv"),
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple:
            if "Episode" in path:
                return episodes, 2
            elif "/File" in path:
                return files, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        entries = service._build_plexmatch_entries(1, ordering_episode_map=None)

        assert len(entries) == 2
        assert entries[0].season_number == 1
        assert entries[0].episode_number == 1
        assert entries[1].season_number == 1
        assert entries[1].episode_number == 2


class TestTmdbOrderingModels:
    """Test TMDB ordering models."""

    def test_tmdb_ordering_defaults(self) -> None:
        o = TmdbOrdering(ordering_id="37854", name="Seasons")
        assert o.ordering_type == 0
        assert o.season_count == 0
        assert o.episode_count == 0
        assert not o.is_default
        assert not o.is_preferred
        assert not o.in_use

    def test_tmdb_ordering_season(self) -> None:
        s = TmdbOrderingSeason(
            season_id="abc123", ordering_id="37854", season_number=1, title="East Blue"
        )
        assert s.season_number == 1
        assert s.title == "East Blue"

    def test_tmdb_ordering_season_no_number(self) -> None:
        """Arc-based orderings may have season_number=None."""
        s = TmdbOrderingSeason(season_id="abc123", ordering_id="sagas", title="East Blue Saga")
        assert s.season_number is None

    def test_tmdb_ordering_episode(self) -> None:
        e = TmdbOrderingEpisode(
            episode_id=852692, season_id="s01", season_number=1, episode_number=1
        )
        assert e.episode_id == 852692
        assert e.season_number == 1
        assert e.episode_number == 1


class TestTmdbOrderingService:
    """Test ShokoService list_tmdb_orderings and fetch_ordering_episode_map."""

    def test_list_tmdb_orderings(self) -> None:
        """Test parsing of ordering list from Shoko API."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        # The /Ordering endpoint returns a plain JSON array, not a paginated response.
        mock_client.get.return_value = [
            {
                "OrderingID": "37854",
                "OrderingName": "Seasons",
                "OrderingType": 1,
                "SeasonCount": 23,
                "EpisodeCount": 1100,
                "IsDefault": True,
                "IsPreferred": False,
                "InUse": True,
            },
            {
                "OrderingID": "62f98314175051007c594bdf",
                "OrderingName": "TVDB Order",
                "OrderingType": 2,
                "SeasonCount": 24,
                "EpisodeCount": 1100,
                "IsDefault": False,
                "IsPreferred": True,
                "InUse": False,
            },
        ]

        orderings = service.list_tmdb_orderings(37854)

        assert len(orderings) == 2
        assert orderings[0].ordering_id == "37854"
        assert orderings[0].name == "Seasons"
        assert orderings[0].season_count == 23
        assert orderings[0].is_default is True
        assert orderings[0].in_use is True
        assert orderings[1].ordering_id == "62f98314175051007c594bdf"
        assert orderings[1].name == "TVDB Order"
        assert orderings[1].is_preferred is True

    def test_fetch_ordering_episode_map(self) -> None:
        """Test building TMDB episode ID → (season, episode) mapping."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        # Season list for the ordering
        seasons_response = [
            {"ID": "s01", "SeasonNumber": 1, "Title": "Romance Dawn"},
            {"ID": "s02", "SeasonNumber": 2, "Title": "Syrup Village"},
        ]
        # Episodes per season
        s01_episodes = [
            {"ID": 852692, "SeasonNumber": 1, "EpisodeNumber": 1, "Title": "Ep1"},
            {"ID": 852693, "SeasonNumber": 1, "EpisodeNumber": 2, "Title": "Ep2"},
        ]
        s02_episodes = [
            {"ID": 852694, "SeasonNumber": 2, "EpisodeNumber": 1, "Title": "Ep3"},
            {"ID": 852695, "SeasonNumber": 2, "EpisodeNumber": 2, "Title": "Ep4"},
        ]

        def mock_get_list(path: str, params: dict | None = None) -> tuple[list, int]:
            if path == "/TMDB/Show/37854/Season":
                return seasons_response, 2
            if path == "/TMDB/Season/s01/Episode":
                return s01_episodes, 2
            if path == "/TMDB/Season/s02/Episode":
                return s02_episodes, 2
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        episode_map = service.fetch_ordering_episode_map(37854, "62f98314175051007c594bdf")

        assert episode_map == {852692: (1, 1), 852693: (1, 2), 852694: (2, 1), 852695: (2, 2)}

    def test_fetch_ordering_skips_none_season_number(self) -> None:
        """Seasons with None season_number (arc-based) are skipped."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        seasons_response = [
            {"ID": "s00", "SeasonNumber": None, "Title": "East Blue Saga"},
            {"ID": "s01", "SeasonNumber": 1, "Title": "Romance Dawn"},
        ]
        s01_episodes = [{"ID": 852692, "SeasonNumber": 1, "EpisodeNumber": 1, "Title": "Ep1"}]

        def mock_get_list(path: str, params: dict | None = None) -> tuple[list, int]:
            if path == "/TMDB/Show/37854/Season":
                return seasons_response, 2
            if path == "/TMDB/Season/s01/Episode":
                return s01_episodes, 1
            return [], 0

        mock_client.get_list.side_effect = mock_get_list

        # Only season with season_number=1 is processed
        episode_map = service.fetch_ordering_episode_map(37854, "62f98314175051007c594bdf")

        assert episode_map == {852692: (1, 1)}

    def test_parse_episode_extracts_tmdb_episode_id(self) -> None:
        """_parse_episode extracts the TMDB episode ID from cross-ref data."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        raw = {
            "ID": 42,
            "Name": "I'm Luffy!",
            "AniDB": {"Type": "Episode", "EpisodeNumber": 1, "ID": 100},
            "TMDB": {"Episodes": [{"SeasonNumber": 1, "EpisodeNumber": 1, "ID": 852692}]},
            "IsHidden": False,
        }

        ep = service._parse_episode(raw)

        assert ep.tmdb_episode_id == 852692
        assert ep.season_number == 1
        assert ep.tmdb_episode_number == 1

    def test_parse_episode_no_tmdb_episode_id(self) -> None:
        """Episodes without TMDB data have tmdb_episode_id=None."""
        mock_client = MagicMock()
        service = ShokoService(mock_client)

        raw = {
            "ID": 50,
            "Name": "OVA Special",
            "AniDB": {"Type": "Episode", "EpisodeNumber": 1, "ID": 5000},
            "TMDB": {"Episodes": []},
            "IsHidden": False,
        }

        ep = service._parse_episode(raw)

        assert ep.tmdb_episode_id is None
