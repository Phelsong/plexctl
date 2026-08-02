"""Diagnostic service for Plex media parsing issues.

Identifies problems like unanalyzed files, cross-season merges,
and missing/inaccessible media that cause incorrect metadata display.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.progress import track

if TYPE_CHECKING:
    from plexapi.video import Show

    from plexctl.client import PlexClient

from plexctl.models import (
    EpisodeDiagnostics,
    MediaPartDetail,
    MediaType,
    SectionDiagnostics,
    ShowDiagnostics,
)


def _plex_show_type() -> type[object]:
    """Return the plexapi Show class lazily for isinstance checks."""
    from plexapi.video import Show

    return Show


logger = logging.getLogger(__name__)


class DiagnosticService:
    """Service for diagnosing Plex media file parsing issues.

    Provides methods to:
    - Scan sections for shows with unanalyzed or mis-parsed media
    - Inspect individual episodes for file details
    - Trigger re-analysis of problem items

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    def scan_section(self, section_title: str, deep: bool = False) -> SectionDiagnostics:
        """Scan a library section for shows with file parsing issues.

        Args:
            section_title: Library section name (e.g. 'Anime').
            deep: If True, include per-episode file details (slower).

        Returns:
            SectionDiagnostics with summary and per-show details.
        """
        section = self._client.server.library.section(section_title)
        section_type = section.type
        if section_type != "show":
            logger.warning(
                "Section '%s' is type '%s', diagnostics are for shows",
                section_title,
                section_type,
            )

        shows = section.all()
        show_diagnostics: list[ShowDiagnostics] = []

        for show in track(shows, description="Processing..."):
            diag = self._diagnose_show(show, deep=deep)
            show_diagnostics.append(diag)

        return SectionDiagnostics(
            key=str(section.key),
            title=section.title,
            section_type=MediaType.from_plex_type(section_type),
            scanner=getattr(section, "scanner", None),
            agent=getattr(section, "agent", None),
            section_locations=list(getattr(section, "locations", [])),
            total_shows=len(shows),
            shows_with_issues=sum(
                1
                for s in show_diagnostics
                if s.unanalyzed_episodes > 0 or s.multi_media_episodes > 0
            ),
            shows=show_diagnostics,
        )

    def diagnose_show(self, rating_key: str | int, deep: bool = False) -> ShowDiagnostics:
        """Diagnose a single show by rating key.

        Args:
            rating_key: Plex rating key for the show.
            deep: If True, include per-episode file details.

        Returns:
            ShowDiagnostics for the specified show.
        """
        key = int(rating_key)
        show = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        if not isinstance(show, _plex_show_type()):
            msg = f"Rating key {key} is a {type(show).__name__}, not a Show"
            raise ValueError(msg)
        return self._diagnose_show(show, deep=deep)  # type: ignore[arg-type]

    def get_episode_details(self, rating_key: str | int) -> EpisodeDiagnostics:
        """Get detailed file information for a single episode.

        Args:
            rating_key: Plex rating key for the episode.

        Returns:
            EpisodeDiagnostics with full file details.
        """
        key = int(rating_key)
        episode = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        return self._episode_to_diagnostics(episode, deep=True)

    def trigger_analyze(self, rating_key: str | int) -> str:
        """Trigger Plex to re-analyze a media item.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            Status message confirming the action.
        """
        key = int(rating_key)
        item = self._client.server.fetchItem(key)  # type: ignore[no-untyped-call]
        item.analyze()
        return f"Analysis triggered for '{getattr(item, 'title', key)}'"

    def trigger_section_analyze(self, section_title: str) -> str:
        """Trigger Plex to re-analyze all items in a section.

        Args:
            section_title: Library section name.

        Returns:
            Status message confirming the action.
        """
        section = self._client.server.library.section(section_title)
        section.analyze()
        return f"Analysis triggered for section '{section_title}'"

    # --- Private helpers ---------------------------------------------------

    def _diagnose_show(self, show: Show, deep: bool = False) -> ShowDiagnostics:
        """Build diagnostics for a single show.

        Args:
            show: plexapi Show object.
            deep: If True, include per-episode file details.

        Returns:
            ShowDiagnostics with episode problems aggregated.
        """
        locations = list(getattr(show, "locations", []))

        # Guard: shows may have no seasons
        seasons = show.seasons()  # type: ignore[no-untyped-call]
        if not seasons:
            return ShowDiagnostics(
                key=str(show.ratingKey),
                title=show.title,
                year=int(show.year) if show.year else None,
                locations=locations,
                total_episodes=0,
            )

        episode_details: list[EpisodeDiagnostics] = []
        unanalyzed_count = 0
        multi_media_count = 0
        missing_file_count = 0
        total_episodes = 0

        for season in seasons:
            episodes = season.episodes()
            for episode in episodes:
                total_episodes += 1
                diag = self._episode_to_diagnostics(episode, deep=deep)

                if diag.has_unanalyzed:
                    unanalyzed_count += 1
                if diag.media_count > 1:
                    multi_media_count += 1
                has_missing = any(
                    part.exists is False or part.accessible is False for part in diag.file_details
                )
                if has_missing:
                    missing_file_count += 1

                episode_details.append(diag)

        return ShowDiagnostics(
            key=str(show.ratingKey),
            title=show.title,
            year=int(show.year) if show.year else None,
            locations=locations,
            total_episodes=total_episodes,
            unanalyzed_episodes=unanalyzed_count,
            multi_media_episodes=multi_media_count,
            missing_file_episodes=missing_file_count,
            episode_details=episode_details,
        )

    @staticmethod
    def _episode_to_diagnostics(episode: object, deep: bool = False) -> EpisodeDiagnostics:
        """Convert a plexapi Episode to EpisodeDiagnostics.

        Args:
            episode: plexapi Episode object.
            deep: If True, populate file_details for each media part.

        Returns:
            EpisodeDiagnostics for the episode.
        """
        key = str(getattr(episode, "ratingKey", "unknown"))
        title = getattr(episode, "title", None)
        sort_title = getattr(episode, "titleSort", None)
        season_number = getattr(episode, "seasonNumber", None)
        episode_number = getattr(episode, "index", None)

        media_list = getattr(episode, "media", [])
        media_count = len(media_list) if media_list else 0

        # Check for unanalyzed media: missing codec info indicates
        # Plex never completed background analysis on this file.
        has_unanalyzed = False
        file_details: list[MediaPartDetail] = []

        if media_list:
            for media in track(media_list):
                video_codec = getattr(media, "videoCodec", None)
                audio_codec = getattr(media, "audioCodec", None)
                container = getattr(media, "container", None)

                if not video_codec and not audio_codec and not container:
                    has_unanalyzed = True

                if not deep:
                    continue

                # Deep scan: extract file-level details from each MediaPart.
                resolution = getattr(media, "videoResolution", None)
                bitrate = getattr(media, "bitrate", None)
                duration = getattr(media, "duration", None)

                parts = getattr(media, "parts", [])
                for part in parts:
                    file_path = getattr(part, "file", "unknown")
                    detail = MediaPartDetail(
                        file_path=file_path,
                        size=getattr(part, "size", None),
                        accessible=getattr(part, "accessible", None),
                        exists=getattr(part, "exists", None),
                        video_codec=video_codec,
                        audio_codec=audio_codec,
                        container=container,
                        resolution=resolution,
                        bitrate=bitrate,
                        duration=duration,
                    )
                    file_details.append(detail)

        return EpisodeDiagnostics(
            key=key,
            title=title,
            sort_title=sort_title,
            season_number=season_number,
            episode_number=episode_number,
            media_count=media_count,
            has_unanalyzed=has_unanalyzed,
            file_details=file_details,
        )
