"""Test diagnostics service for plexctl."""

from unittest.mock import MagicMock

from plexctl.services.diagnostics import DiagnosticService


def _make_mock_episode(
    rating_key: str = "100",
    title: str = "Episode 1",
    season_number: int = 1,
    episode_number: int = 1,
    media_count: int = 1,
    unanalyzed: bool = False,
    file_paths: list[str] | None = None,
) -> MagicMock:
    """Create a mock plexapi Episode object."""
    episode = MagicMock()
    episode.ratingKey = rating_key
    episode.title = title
    episode.titleSort = title
    episode.seasonNumber = season_number
    episode.index = episode_number

    if media_count == 0:
        episode.media = []
        return episode

    media_objects = []
    for _i in range(media_count):
        media = MagicMock()
        media.videoCodec = None if unanalyzed else "h264"
        media.audioCodec = None if unanalyzed else "aac"
        media.container = None if unanalyzed else "mkv"
        media.videoResolution = "1080"
        media.bitrate = 5000
        media.duration = 1440000

        parts = []
        if file_paths:
            for path in file_paths:
                part = MagicMock()
                part.file = path
                part.size = 1000000000
                part.accessible = True
                part.exists = True
                parts.append(part)
        else:
            part = MagicMock()
            part.file = f"/data/show/s{season_number:02d}e{episode_number:02d}.mkv"
            part.size = 1000000000
            part.accessible = True
            part.exists = True
            parts.append(part)

        media.parts = parts
        media_objects.append(media)

    episode.media = media_objects
    return episode


def _make_mock_season(episodes: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock plexapi Season object."""
    season = MagicMock()
    season.episodes.return_value = episodes or []
    return season


def _make_mock_show(
    rating_key: str = "10",
    title: str = "Test Show",
    year: int = 2024,
    locations: list[str] | None = None,
    seasons: list[MagicMock] | None = None,
) -> MagicMock:
    """Create a mock plexapi Show object."""
    show = MagicMock()
    show.ratingKey = rating_key
    show.title = title
    show.year = year
    show.locations = locations or ["/data/show"]
    show.seasons.return_value = seasons or []
    return show


class TestEpisodeToDiagnostics:
    """Tests for _episode_to_diagnostics static method."""

    def test_basic_episode(self) -> None:
        """Should convert a simple episode with one media."""
        episode = _make_mock_episode()
        result = DiagnosticService._episode_to_diagnostics(episode, deep=False)

        assert result.key == "100"
        assert result.title == "Episode 1"
        assert result.season_number == 1
        assert result.episode_number == 1
        assert result.media_count == 1
        assert result.has_unanalyzed is False

    def test_unanalyzed_episode(self) -> None:
        """Should detect unanalyzed media missing codec info."""
        episode = _make_mock_episode(unanalyzed=True)
        result = DiagnosticService._episode_to_diagnostics(episode, deep=False)

        assert result.has_unanalyzed is True

    def test_multiple_media_versions(self) -> None:
        """Should count multiple media objects as separate versions."""
        episode = _make_mock_episode(media_count=3)
        result = DiagnosticService._episode_to_diagnostics(episode, deep=False)

        assert result.media_count == 3

    def test_deep_scan_populates_file_details(self) -> None:
        """Deep scan should populate file details for each media part."""
        ep = _make_mock_episode(media_count=1, file_paths=["/data/anime/show/s01e01.mkv"])
        result = DiagnosticService._episode_to_diagnostics(ep, deep=True)

        assert len(result.file_details) == 1
        detail = result.file_details[0]
        assert detail.file_path == "/data/anime/show/s01e01.mkv"
        assert detail.video_codec == "h264"
        assert detail.audio_codec == "aac"
        assert detail.container == "mkv"

    def test_no_media_objects(self) -> None:
        """Should handle episodes with no media gracefully."""
        episode = _make_mock_episode(media_count=0)
        result = DiagnosticService._episode_to_diagnostics(episode, deep=False)

        assert result.media_count == 0
        assert result.has_unanalyzed is False


class TestDiagnoseShow:
    """Tests for _diagnose_show method."""

    def test_show_with_no_seasons(self) -> None:
        """Should handle a show with no seasons."""
        show = _make_mock_show(seasons=[])
        service = MagicMock()
        diag = DiagnosticService.__new__(DiagnosticService)
        diag._client = service  # type: ignore[assignment]

        result = diag._diagnose_show(show, deep=False)

        assert result.total_episodes == 0
        assert result.unanalyzed_episodes == 0

    def test_show_with_unanalyzed_episodes(self) -> None:
        """Should count unanalyzed episodes correctly."""
        ep1 = _make_mock_episode(rating_key="1", title="EP1", unanalyzed=True)
        ep2 = _make_mock_episode(rating_key="2", title="EP2")
        season = _make_mock_season(episodes=[ep1, ep2])
        show = _make_mock_show(seasons=[season])

        service = MagicMock()
        diag = DiagnosticService.__new__(DiagnosticService)
        diag._client = service  # type: ignore[assignment]

        result = diag._diagnose_show(show, deep=False)

        assert result.total_episodes == 2
        assert result.unanalyzed_episodes == 1
