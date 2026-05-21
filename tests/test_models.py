"""Test models for plexctl."""
from plexctl.models import (
    BatchEditResult,
    BatchFixResult,
    CollectionInfo,
    EpisodeDiagnostics,
    LibrarySection,
    MediaMetadata,
    MediaPartDetail,
    MediaType,
    MetadataEdit,
    ReorgAction,
    ReorganizePlan,
    SectionDiagnostics,
    ShowDiagnostics,
)


def test_media_type_values() -> None:
    """MediaType enum should have expected values."""
    assert MediaType.MOVIE.value == "movie"
    assert MediaType.SHOW.value == "show"
    assert MediaType.EPISODE.value == "episode"


def test_metadata_edit_model() -> None:
    """MetadataEdit should store field and value."""
    edit = MetadataEdit(field="title", value="New Title")
    assert edit.field == "title"
    assert edit.value == "New Title"


def test_media_metadata_model() -> None:
    """MediaMetadata should accept all optional fields as None."""
    metadata = MediaMetadata(key="12345", title="Test Movie")
    assert metadata.key == "12345"
    assert metadata.title == "Test Movie"
    assert metadata.year is None
    assert metadata.summary is None
    assert metadata.media_type is None


def test_media_metadata_full() -> None:
    """MediaMetadata should accept all fields populated."""
    metadata = MediaMetadata(
        key="12345",
        title="Test Movie",
        year=2024,
        summary="A great movie",
        rating=8.5,
        audience_rating=9.0,
        content_rating="R",
        media_type=MediaType.MOVIE,
    )
    assert metadata.year == 2024
    assert metadata.rating == 8.5
    assert metadata.media_type == MediaType.MOVIE


def test_batch_edit_result_defaults() -> None:
    """BatchEditResult should default to zero counts."""
    result = BatchEditResult()
    assert result.total == 0
    assert result.updated == 0
    assert result.failed == 0
    assert result.errors == {}


def test_collection_info_model() -> None:
    """CollectionInfo should store collection metadata."""
    info = CollectionInfo(key="1", title="Best Movies", smart=True, content_count=15)
    assert info.title == "Best Movies"
    assert info.smart is True
    assert info.content_count == 15


def test_library_section_model() -> None:
    """LibrarySection should store section metadata."""
    section = LibrarySection(
        key="1", title="Movies", section_type=MediaType.MOVIE, count=500
    )
    assert section.title == "Movies"
    assert section.section_type == MediaType.MOVIE
    assert section.count == 500


# --- Diagnostic model tests -----------------------------------------------


def test_media_type_from_plex_type() -> None:
    """MediaType.from_plex_type should return correct enum or None."""
    assert MediaType.from_plex_type("movie") == MediaType.MOVIE
    assert MediaType.from_plex_type("show") == MediaType.SHOW
    assert MediaType.from_plex_type("photo") == MediaType.PHOTO
    assert MediaType.from_plex_type("unknown") is None


def test_media_part_detail_defaults() -> None:
    """MediaPartDetail should default optional fields to None."""
    detail = MediaPartDetail(file_path="/data/anime/show/ep1.mkv")
    assert detail.file_path == "/data/anime/show/ep1.mkv"
    assert detail.size is None
    assert detail.accessible is None
    assert detail.exists is None
    assert detail.video_codec is None
    assert detail.audio_codec is None
    assert detail.container is None


def test_episode_diagnostics_unanalyzed() -> None:
    """EpisodeDiagnostics should track unanalyzed state."""
    ep = EpisodeDiagnostics(
        key="123",
        title="Episode 1",
        season_number=1,
        episode_number=1,
        media_count=1,
        has_unanalyzed=True,
    )
    assert ep.has_unanalyzed is True
    assert ep.media_count == 1
    assert ep.file_details == []


def test_show_diagnostics_aggregation() -> None:
    """ShowDiagnostics should aggregate episode counts."""
    show = ShowDiagnostics(
        key="456",
        title="Test Show",
        year=2024,
        locations=["/data/anime/test"],
        total_episodes=12,
        unanalyzed_episodes=3,
        multi_media_episodes=2,
        missing_file_episodes=1,
    )
    assert show.total_episodes == 12
    assert show.unanalyzed_episodes == 3
    assert show.multi_media_episodes == 2
    assert show.missing_file_episodes == 1
    assert show.locations == ["/data/anime/test"]


def test_section_diagnostics_summary() -> None:
    """SectionDiagnostics should aggregate show-level problems."""
    section = SectionDiagnostics(
        key="22",
        title="Anime",
        section_type=MediaType.SHOW,
        scanner="Plex TV Series",
        agent="tv.plex.agents.series",
        section_locations=["/data/anime"],
        total_shows=51,
        shows_with_issues=36,
    )
    assert section.title == "Anime"
    assert section.total_shows == 51
    assert section.shows_with_issues == 36
    assert section.section_type == MediaType.SHOW


def test_batch_fix_result_defaults() -> None:
    """BatchFixResult should default to empty counts."""
    result = BatchFixResult()
    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.results == []


def test_batch_fix_result_with_failures() -> None:
    """BatchFixResult should track failures."""
    from plexctl.models import FixResult

    failure = FixResult(
        key="99",
        title="Broken Show",
        action="batch-analyze",
        success=False,
        error="Timeout",
    )
    result = BatchFixResult(total=5, succeeded=4, failed=1, results=[failure])
    assert result.total == 5
    assert result.succeeded == 4
    assert result.failed == 1
    assert result.results[0].error == "Timeout"


def test_reorg_action() -> None:
    """ReorgAction should store action details."""
    action = ReorgAction(
        action="move",
        source="/mnt/nfs/media/anime/Arifureta/S2",
        destination="/mnt/nfs/media/anime/Arifureta S2",
        reason="Move season to top-level",
        risk="medium",
    )
    assert action.action == "move"
    assert action.destination is not None
    assert action.risk == "medium"


def test_reorg_action_review() -> None:
    """ReorgAction with review type should have no destination."""
    action = ReorgAction(
        action="review",
        source="/data/anime/Sword Art Online",
        reason="Multi-location show needs Shoko review",
        risk="high",
    )
    assert action.action == "review"
    assert action.destination is None
    assert action.risk == "high"


def test_reorganize_plan() -> None:
    """ReorganizePlan should aggregate actions and summary."""
    plan = ReorganizePlan(
        section_title="Anime",
        total_actions=2,
        actions=[
            ReorgAction(
                action="move",
                source="/source",
                destination="/dest",
                reason="test",
                risk="low",
            ),
            ReorgAction(
                action="review", source="/source2", reason="review needed", risk="high"
            ),
        ],
        summary="2 actions proposed",
    )
    assert plan.section_title == "Anime"
    assert plan.total_actions == 2
    assert len(plan.actions) == 2
    assert plan.actions[0].action == "move"
    assert plan.actions[1].action == "review"
