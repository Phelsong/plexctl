"""CSV serialization and deserialization for Pydantic models.

Provides bidirectional CSV support: any Pydantic model can be written to CSV
(and read back) with automatic handling of nested models, enums, and list fields.

Design principles (Parse Don't Validate):
  - CSV output is flat: nested models are flattened with dot-separated keys
  - Lists are joined with `|` separator (configurable)
  - Enums are stored by value
  - Optional fields that are None produce empty cells
  - Reading CSV validates through Pydantic, rejecting malformed rows
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Sequence

T = TypeVar("T", bound=BaseModel)

LIST_SEPARATOR = "|"
NESTED_SEPARATOR = "."


def _flatten_model(model: BaseModel, prefix: str = "") -> dict[str, str]:
    """Flatten a Pydantic model into a flat dict of string values.

    Nested models get dot-separated keys. Lists are joined with LIST_SEPARATOR.
    Enums are converted to their values. None values become empty strings.
    """
    result: dict[str, str] = {}

    for field_name in type(model).model_fields:
        value = getattr(model, field_name)
        key = f"{prefix}{NESTED_SEPARATOR}{field_name}" if prefix else field_name

        if value is None:
            result[key] = ""
        elif isinstance(value, BaseModel):
            result.update(_flatten_model(value, prefix=key))
        elif isinstance(value, list):
            # Convert list items to strings, handling nested models
            items: list[str] = []
            for item in value:
                if isinstance(item, BaseModel):
                    # Represent nested models in lists as JSON-like string
                    items.append(item.model_dump_json())
                else:
                    items.append(str(item))
            result[key] = LIST_SEPARATOR.join(items)
        elif hasattr(value, "value"):
            # StrEnum or other enum with .value
            result[key] = str(value.value)
        else:
            result[key] = str(value)

    return result


def _get_headers(models: Sequence[BaseModel]) -> list[str]:
    """Extract CSV headers from a list of models.

    Uses the first model to determine headers, preserving order.
    """
    if not models:
        return []
    headers = list(_flatten_model(models[0]).keys())
    # Collect any additional headers from remaining models
    for model in models[1:]:
        for key in _flatten_model(model):
            if key not in headers:
                headers.append(key)
    return headers


def to_csv(
    models: Sequence[BaseModel],
    output: Path | None = None,
    include_headers: bool = True,
) -> str:
    """Convert a list of Pydantic models to CSV.

    Args:
        models: List of Pydantic model instances.
        output: File path to write CSV. If None, returns CSV string.
        include_headers: Whether to include headers in output.

    Returns:
        CSV string (always, even when writing to file).
    """
    if not models:
        csv_content = ""
        if output:
            output.write_text(csv_content)
        return csv_content

    headers = _get_headers(models)
    rows = [_flatten_model(model) for model in models]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    if include_headers:
        writer.writeheader()
    writer.writerows(rows)

    csv_content = buf.getvalue()

    if output:
        output.write_text(csv_content)

    return csv_content


def from_csv[T: BaseModel](
    model_class: type[T],
    csv_data: str | Path,
) -> list[T]:
    """Parse CSV data into a list of Pydantic model instances.

    Args:
        model_class: The Pydantic model class to deserialize into.
        csv_data: CSV string or path to a CSV file.

    Returns:
        List of validated model instances.

    Raises:
        ValidationError: If any row doesn't match the model schema.
    """
    if isinstance(csv_data, Path):
        csv_data = csv_data.read_text()

    if not csv_data.strip():
        return []

    reader = csv.DictReader(io.StringIO(csv_data))
    models: list[T] = []

    for row in reader:
        # Unflatten dot-separated keys into nested dicts
        nested: dict[str, Any] = {}
        for key, value in row.items():
            if key is None:
                continue
            if NESTED_SEPARATOR in key:
                # Split into nested dict path
                parts = key.split(NESTED_SEPARATOR)
                current = nested
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value if value != "" else None
            elif value != "":
                # Only include non-empty values; let Pydantic defaults handle empty
                nested[key] = value

        models.append(model_class.model_validate(nested))

    return models


# --- Model registry for ingest command ---

_MODEL_REGISTRY: dict[str, type[BaseModel]] = {}


def register_model(name: str, model_class: type[BaseModel]) -> None:
    """Register a model class for CSV ingest by name."""
    _MODEL_REGISTRY[name] = model_class


def get_model_class(name: str) -> type[BaseModel] | None:
    """Look up a registered model class by name."""
    return _MODEL_REGISTRY.get(name)


def list_model_names() -> list[str]:
    """List all registered model names."""
    return sorted(_MODEL_REGISTRY.keys())


def write_csv_to_output(
    models: Sequence[BaseModel],
    output: str | None = None,
) -> None:
    """Write models as CSV to either a file or stdout.

    A convenience wrapper around to_csv() that handles the common
    CLI pattern of '--output FILE' or stdout.
    """
    csv_content = to_csv(models, output=Path(output) if output else None)

    if not output:
        # Write to stdout (skip if already written to file)
        sys.stdout.write(csv_content)


# --- Register all CSV models for ingest ---


def _register_all_csv_models() -> None:
    """Register all Csv* models so the ingest command can look them up."""
    from plexctl.models import (
        CsvAlbumInfo,
        CsvArtistInfo,
        CsvBandwidthStats,
        CsvButlerTask,
        CsvCollectionInfo,
        CsvCollectionMetadata,
        CsvCrcAuditResult,
        CsvEpisodeDiagnostics,
        CsvFsDir,
        CsvLibraryLocation,
        CsvLibrarySection,
        CsvMediaMetadata,
        CsvMediaPartDetail,
        CsvMediaTreeItem,
        CsvPhotoAlbumInfo,
        CsvPhotoInfo,
        CsvPlaybackSession,
        CsvPlaylist,
        CsvPlaylistItem,
        CsvResourceStats,
        CsvSearchResult,
        CsvSeasonGap,
        CsvServerInfo,
        CsvServerPreference,
        CsvShokoEpisode,
        CsvShokoFile,
        CsvShokoMismatch,
        CsvShokoSeries,
        CsvShowDiagnostics,
        CsvSimilarMedia,
        CsvSmartPlaylist,
        CsvSmartPlaylistFilter,
        CsvSubtitleStreamInfo,
        CsvTmdbSearchResult,
        CsvTrackInfo,
        CsvTranscodeSessionInfo,
        CsvTriageIssue,
        CsvUpdateInfo,
        CsvWatchHistoryEntry,
    )

    _MODEL_REGISTRY.update(
        {
            "media_metadata": CsvMediaMetadata,
            "library_section": CsvLibrarySection,
            "library_location": CsvLibraryLocation,
            "collection_info": CsvCollectionInfo,
            "collection_metadata": CsvCollectionMetadata,
            "media_tree_item": CsvMediaTreeItem,
            "show_diagnostics": CsvShowDiagnostics,
            "triage_issue": CsvTriageIssue,
            "season_gap": CsvSeasonGap,
            "shoko_series": CsvShokoSeries,
            "shoko_file": CsvShokoFile,
            "shoko_mismatch": CsvShokoMismatch,
            "shoko_episode": CsvShokoEpisode,
            "episode_diagnostics": CsvEpisodeDiagnostics,
            "media_part_detail": CsvMediaPartDetail,
            "tmdb_search_result": CsvTmdbSearchResult,
            "fs_dir": CsvFsDir,
            "crc_audit_result": CsvCrcAuditResult,
            "playback_session": CsvPlaybackSession,
            "server_preference": CsvServerPreference,
            "server_info": CsvServerInfo,
            "butler_task": CsvButlerTask,
            "search_result": CsvSearchResult,
            "similar_media": CsvSimilarMedia,
            "smart_playlist": CsvSmartPlaylist,
            "smart_playlist_filter": CsvSmartPlaylistFilter,
            "playlist": CsvPlaylist,
            "playlist_item": CsvPlaylistItem,
            "artist": CsvArtistInfo,
            "album": CsvAlbumInfo,
            "track": CsvTrackInfo,
            "photo_album": CsvPhotoAlbumInfo,
            "photo": CsvPhotoInfo,
            "transcode_session": CsvTranscodeSessionInfo,
            "watch_history_entry": CsvWatchHistoryEntry,
            "subtitle_stream": CsvSubtitleStreamInfo,
            "update_info": CsvUpdateInfo,
            "bandwidth_stats": CsvBandwidthStats,
            "resource_stats": CsvResourceStats,
        }
    )


_register_all_csv_models()
