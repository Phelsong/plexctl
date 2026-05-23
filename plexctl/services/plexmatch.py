"""Generic PlexMatch service using Plex metadata.

Generates .plexmatch files from Plex show metadata and file paths
without requiring any external metadata source.
"""

from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from plexctl.models import PlexMatch, PlexMatchBatchResult, PlexMatchEntry, PlexMatchResult

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)

# Pattern to extract external IDs from Plex GUIDs
_GUID_PATTERNS = {
    "tmdb": re.compile(r"tmdb://(\d+)"),
    "tvdb": re.compile(r"(?:thetvdb|tvdb)://(\d+)"),
    "imdb": re.compile(r"imdb://(tt\d+)"),
}


class PlexMatchService:
    """Generate .plexmatch files using Plex metadata."""

    def __init__(self, plex_client: PlexClient) -> None:
        self._client = plex_client

    def generate_plexmatch(
        self,
        rating_key: str | int,
        plexmatch_dir: str | None = None,
        *,
        append: bool = False,
        append_dir: str | None = None,
    ) -> PlexMatch:
        """Generate a PlexMatch for a show using only Plex metadata.

        Args:
            rating_key: Plex rating key for the show.
            plexmatch_dir: Base directory for computing relative file paths.
                           If None, uses absolute paths as-is.
            append: If True and the target .plexmatch file exists, merge
                    existing entries with new ones (new entries override
                    duplicates).
            append_dir: Full path to the directory containing the .plexmatch
                file for append mode. When not provided, falls back to
                plexmatch_dir.

        Returns:
            PlexMatch model with show metadata and episode mappings.
        """
        server = self._client.server
        show = server.fetchItem(int(rating_key))  # type: ignore[no-untyped-call]

        if show.type != "show":
            msg = f"Rating key {rating_key} is not a show (type: {show.type})"
            raise ValueError(msg)

        # Extract metadata
        title = show.title
        year = show.year
        guids = self._parse_guids(show)

        # Get all episodes with file paths
        entries = self._build_entries(show, plexmatch_dir)

        plexmatch = PlexMatch(
            title=title,
            year=year,
            tmdb_id=guids.get("tmdb"),  # type: ignore[arg-type]
            tvdb_id=guids.get("tvdb"),  # type: ignore[arg-type]
            imdb_id=guids.get("imdb"),  # type: ignore[arg-type]
            entries=entries,
        )

        if append:
            read_dir = append_dir or plexmatch_dir
            if read_dir:
                existing = self._read_existing_plexmatch(read_dir)
                if existing is not None:
                    plexmatch = plexmatch.merge(existing)

        return plexmatch

    def generate_plexmatch_batch(
        self,
        section: str = "Anime",
        plexmatch_dir: str | None = None,
        dry_run: bool = False,
        *,
        append: bool = False,
    ) -> PlexMatchBatchResult:
        """Generate .plexmatch files for all shows in a section.

        Args:
            section: Library section name.
            plexmatch_dir: Base directory for computing relative paths.
            dry_run: If True, only report what would be done.
            append: If True and the target .plexmatch file exists, merge
                    existing entries with new ones (new entries override
                    duplicates).

        Returns:
            PlexMatchBatchResult with per-show results.
        """
        server = self._client.server
        section_obj = server.library.section(section)
        shows = section_obj.all()

        result = PlexMatchBatchResult(total_dirs=len(shows))

        for show in shows:
            try:
                # Use the show's actual directory as append_dir so
                # _read_existing_plexmatch can find the file
                show_dir = show.locations[0] if show.locations else None
                plexmatch = self.generate_plexmatch(
                    show.ratingKey,
                    plexmatch_dir=plexmatch_dir,
                    append=append,
                    append_dir=show_dir,
                )
                result.results.append(
                    PlexMatchResult(
                        show_key=str(show.ratingKey),
                        show_name=show.title,
                        folder_name=(
                            Path(show.locations[0]).name if show.locations else show.title
                        ),
                        folder_path=show.locations[0] if show.locations else "",
                        success=True,
                        entry_count=len(plexmatch.entries),
                    )
                )
                result.matched += 1
                result.generated += 1
            except Exception as e:
                result.results.append(
                    PlexMatchResult(
                        show_key=str(show.ratingKey),
                        show_name=show.title,
                        success=False,
                        error=str(e),
                    )
                )
                result.failed += 1
                logger.warning("Failed to generate plexmatch for %s: %s", show.title, e)

        return result

    @staticmethod
    def _parse_guids(show: Any) -> dict[str, int | str | None]:
        """Extract external IDs from Plex GUIDs.

        Plex stores GUIDs like:
          com.plexapp.agents.thetvdb://37854?lang=en
          tmdb://1234
          com.plexapp.agents.imdb://tt1234567?lang=en
        """
        result: dict[str, int | str | None] = {}
        guids = getattr(show, "guids", []) or []

        # Also check the main guid field
        main_guid = getattr(show, "guid", "") or ""
        all_guids = [*list(guids), main_guid] if main_guid else list(guids)

        for guid_obj in all_guids:
            guid_str = str(
                getattr(guid_obj, "id", guid_obj) if not isinstance(guid_obj, str) else guid_obj
            )
            for key, pattern in _GUID_PATTERNS.items():
                match = pattern.search(guid_str)
                if match:
                    value = match.group(1)
                    result[key] = int(value) if key != "imdb" else value

        return result

    @staticmethod
    def _build_entries(show: Any, plexmatch_dir: str | None = None) -> list[PlexMatchEntry]:
        """Build episode entries from Plex show data.

        Walks show.seasons() → season.episodes() → episode.media → parts
        to extract file paths and season/episode numbers.
        """
        entries: list[PlexMatchEntry] = []

        for season in show.seasons():
            season_num = season.index
            if season_num is None or season_num == 0:
                continue  # Skip specials (season 0) and unknowns

            for episode in season.episodes():
                ep_num = episode.index
                if ep_num is None:
                    continue

                # Get file paths from media parts
                for media in episode.media:
                    for part in media.parts:
                        file_path = part.file
                        if file_path and plexmatch_dir:
                            with contextlib.suppress(ValueError):
                                file_path = str(Path(file_path).relative_to(plexmatch_dir))

                        entries.append(
                            PlexMatchEntry(
                                season_number=season_num,
                                episode_number=ep_num,
                                filename=Path(file_path).name if file_path else "",
                            )
                        )

        return entries

    @staticmethod
    def _read_existing_plexmatch(target_dir: str) -> PlexMatch | None:
        """Read an existing .plexmatch file from the target directory.

        Args:
            target_dir: Directory where .plexmatch would be written.

        Returns:
            Parsed PlexMatch if the file exists, None otherwise.
        """
        plexmatch_path = Path(target_dir) / ".plexmatch"
        if plexmatch_path.is_file():
            content = plexmatch_path.read_text(encoding="utf-8")
            return PlexMatch.parse(content)
        return None
