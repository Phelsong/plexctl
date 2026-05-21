"""Shoko plugin CSV converters.

Converts Shoko-specific Pydantic models to flat CSV-exportable row models.
"""

from __future__ import annotations

from plexctl.models import (
    CrcAuditResult,
    CsvCrcAuditResult,
    CsvShokoEpisode,
    CsvShokoFile,
    CsvShokoMismatch,
    CsvShokoSeries,
    CsvTmdbSearchResult,
    ShokoEpisode,
    ShokoFile,
    ShokoMismatch,
    ShokoSeries,
    TmdbSearchResult,
)


def shoko_series_to_csv(series: ShokoSeries) -> CsvShokoSeries:
    """Convert ShokoSeries to a flat CSV row."""
    return CsvShokoSeries(
        id=str(series.ids.id),
        name=series.name,
        anidb=str(series.ids.anidb) if series.ids.anidb else "",
        episode_count=str(series.episode_count),
        tmdb_shows="|".join(str(t) for t in series.ids.tmdb_show),
        tmdb_movies="|".join(str(t) for t in series.ids.tmdb_movie),
        local_episodes=str(series.local_sizes.episodes),
        local_specials=str(series.local_sizes.specials),
    )


def shoko_file_to_csv(file: ShokoFile) -> CsvShokoFile:
    """Convert ShokoFile to a flat CSV row."""
    return CsvShokoFile(
        id=str(file.id),
        filename=file.filename or "",
        relative_path=file.relative_path or "",
        series_name=file.series_name or "",
        resolution=file.resolution or "",
        is_variation=str(file.is_variation),
        is_ignored=str(file.is_ignored),
        is_accessible=str(file.is_accessible),
        crc32=file.crc32 or "",
        ed2k=file.ed2k or "",
        sha1=file.sha1 or "",
    )


def shoko_mismatch_to_csv(mismatch: ShokoMismatch) -> CsvShokoMismatch:
    """Convert ShokoMismatch to a flat CSV row."""
    return CsvShokoMismatch(
        mismatch_type=mismatch.mismatch_type,
        shoko_id=str(mismatch.shoko_id) if mismatch.shoko_id else "",
        name=mismatch.name or "",
        detail=mismatch.detail,
        severity=mismatch.severity,
        plex_key=mismatch.plex_key or "",
    )


def shoko_episode_to_csv(episode: ShokoEpisode) -> CsvShokoEpisode:
    """Convert ShokoEpisode to a flat CSV row."""
    return CsvShokoEpisode(
        id=str(episode.id),
        name=episode.name or "",
        episode_number=str(episode.episode_number) if episode.episode_number else "",
        episode_type=episode.episode_type.value,
        season_number=str(episode.season_number) if episode.season_number else "",
        anidb_id=str(episode.anidb_id) if episode.anidb_id else "",
        is_hidden=str(episode.is_hidden),
    )


def tmdb_search_result_to_csv(result: TmdbSearchResult) -> CsvTmdbSearchResult:
    """Convert TmdbSearchResult to a flat CSV row."""
    return CsvTmdbSearchResult(
        id=str(result.id),
        name=result.name,
        overview=(result.overview or "").replace("\n", " ").strip(),
        year=str(result.year) if result.year else "",
        first_aired=result.first_aired or "",
        poster_url=result.poster_url or "",
    )


def crc_audit_to_csv(result: CrcAuditResult) -> CsvCrcAuditResult:
    """Convert CrcAuditResult to a flat CSV row."""
    return CsvCrcAuditResult(
        series_id=str(result.series_id),
        series_name=result.series_name,
        total_files=str(result.total_files),
        files_with_crc=str(result.files_with_crc),
        files_missing_crc=str(result.files_missing_crc),
        files_no_bracket=str(result.files_no_bracket),
        missing_crc_paths="|".join(result.missing_crc_paths),
    )
