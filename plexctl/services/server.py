"""Server service for Plex server administration and playback sessions.

Provides high-level operations for:
- Viewing active playback sessions
- Rating media items
- Marking items as watched/unwatched
- Emptying section trash
- Deleting items
- Merging media items
- Server info and preferences
- Butler (background task) management
- Watch history and progress
- On Deck, Recently Added, Continue Watching
- Transcode session management

Uses PlexHTTPClient for endpoints that plexapi does not expose,
and PlexClient.server for operations plexapi already supports.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from plexctl.client import PlexHTTPClient
from plexctl.models import (
    BandwidthStats,
    ButlerTask,
    FixResult,
    MediaMetadata,
    MediaType,
    PlaybackSession,
    ResourceStats,
    ServerInfo,
    ServerPreference,
    TranscodeSessionInfo,
    UpdateInfo,
    WatchHistoryEntry,
)

if TYPE_CHECKING:
    from plexctl.client import PlexClient

logger = logging.getLogger(__name__)


class ServerService:
    """Service for Plex server administration and playback sessions.

    Args:
        client: Connected PlexClient instance.
    """

    def __init__(self, client: PlexClient) -> None:
        self._client = client

    # --- Playback sessions --------------------------------------------------

    def list_sessions(self) -> list[PlaybackSession]:
        """List all active playback sessions on the server.

        Returns:
            List of PlaybackSession for each active session.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        data = http.get("/status/sessions")

        if data is None:
            return []

        media_container = data.get("MediaContainer", data)
        raw_metadata = media_container.get("Metadata", [])

        if isinstance(raw_metadata, dict):
            metadata_list: list[dict[str, Any]] = [raw_metadata]
        elif isinstance(raw_metadata, list):
            metadata_list = raw_metadata
        else:
            metadata_list = []

        sessions: list[PlaybackSession] = []
        for item in metadata_list:
            player = item.get("Player", {}) or {}
            if isinstance(player, list):
                player = player[0] if player else {}
            user_info = item.get("User", {}) or {}
            if isinstance(user_info, list):
                user_info = user_info[0] if user_info else {}
            raw_transcode = item.get("TranscodeSession")
            transcode = raw_transcode is not None
            raw_media = item.get("Media", [])
            if isinstance(raw_media, list) and raw_media:
                media_info = raw_media[0]
            elif isinstance(raw_media, dict):
                media_info = raw_media
            else:
                media_info = {}

            raw_video = media_info.get("VideoStream", {}) or {}
            if isinstance(raw_video, list) and raw_video:
                video_info: dict[str, Any] = raw_video[0]
            elif isinstance(raw_video, dict):
                video_info = raw_video
            else:
                video_info = {}

            raw_audio = media_info.get("AudioStream", {}) or {}
            if isinstance(raw_audio, list) and raw_audio:
                audio_info: dict[str, Any] = raw_audio[0]
            elif isinstance(raw_audio, dict):
                audio_info = raw_audio
            else:
                audio_info = {}

            duration = _safe_int(item.get("duration"))
            view_offset = _safe_int(item.get("viewOffset"))
            bitrate_val = _safe_int(media_info.get("bitrate"))

            sessions.append(
                PlaybackSession(
                    session_key=str(item.get("sessionKey", item.get("ratingKey", ""))),
                    user=user_info.get("title", ""),
                    player_title=player.get("title", ""),
                    player_address=player.get("address", ""),
                    state=player.get("state", ""),
                    media_type=item.get("type", ""),
                    title=item.get("title", ""),
                    grandparent_title=item.get("grandparentTitle"),
                    parent_title=item.get("parentTitle"),
                    rating_key=str(item.get("ratingKey", "")),
                    duration=duration,
                    view_offset=view_offset,
                    bitrate=bitrate_val,
                    video_codec=_first_str(video_info, "codec"),
                    audio_codec=_first_str(audio_info, "codec"),
                    container=media_info.get("container"),
                    transcoding=transcode,
                )
            )

        return sessions

    # --- Rating -------------------------------------------------------------

    def rate(self, rating_key: str | int, rating: float) -> FixResult:
        """Set the user rating for a media item.

        Args:
            rating_key: Plex rating key for the item.
            rating: Rating value (typically 0-10).

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        key = str(rating_key)
        http = PlexHTTPClient(self._client)

        try:
            http.put(
                "/:/rate",
                params={
                    "key": key,
                    "identifier": "com.plexapp.plugins.library",
                    "rating": str(rating),
                },
            )
        except Exception as exc:
            return FixResult(key=key, action="rate", success=False, error=str(exc))

        return FixResult(key=key, action="rate", success=True)

    # --- Watch state --------------------------------------------------------

    def scrobble(self, rating_key: str | int) -> FixResult:
        """Mark a media item as watched.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        key = str(rating_key)
        http = PlexHTTPClient(self._client)

        try:
            http.put(
                "/:/scrobble", params={"key": key, "identifier": "com.plexapp.plugins.library"}
            )
        except Exception as exc:
            return FixResult(key=key, action="scrobble", success=False, error=str(exc))

        return FixResult(key=key, action="scrobble", success=True)

    def unscrobble(self, rating_key: str | int) -> FixResult:
        """Mark a media item as unwatched.

        Args:
            rating_key: Plex rating key for the item.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        key = str(rating_key)
        http = PlexHTTPClient(self._client)

        try:
            http.put(
                "/:/unscrobble", params={"key": key, "identifier": "com.plexapp.plugins.library"}
            )
        except Exception as exc:
            return FixResult(key=key, action="unscrobble", success=False, error=str(exc))

        return FixResult(key=key, action="unscrobble", success=True)

    # --- Library management -------------------------------------------------

    def empty_trash(self, section_key: str | int) -> FixResult:
        """Empty the trash for a library section.

        Args:
            section_key: Library section key (use list_sections to find it).

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        key = str(section_key)
        http = PlexHTTPClient(self._client)

        try:
            http.put(f"/library/sections/{key}/emptyTrash")
        except Exception as exc:
            return FixResult(key=key, action="empty-trash", success=False, error=str(exc))

        return FixResult(key=key, action="empty-trash", success=True)

    def delete_item(self, rating_key: str | int) -> FixResult:
        """Delete a media item from the library.

        Args:
            rating_key: Plex rating key for the item to delete.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        key = str(rating_key)
        http = PlexHTTPClient(self._client)
        title = "(unknown)"

        try:
            try:
                item = self._client.server.fetchItem(int(key))  # type: ignore[no-untyped-call]
                title = getattr(item, "title", "(unknown)")
            except Exception as exc:
                logger.debug("Could not fetch title for rating key %s: %s", key, exc)

            http.delete(f"/library/metadata/{key}")
        except Exception as exc:
            return FixResult(key=key, title=title, action="delete", success=False, error=str(exc))

        return FixResult(key=key, title=title, action="delete", success=True)

    def merge(self, target_key: str | int, source_keys: list[str | int]) -> FixResult:
        """Merge multiple media items into one.

        The target item absorbs the source items. All source items
        are removed and their media is moved to the target.

        Args:
            target_key: The rating key of the item to merge into.
            source_keys: Rating keys of items to merge from.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        target = str(target_key)
        sources = ",".join(str(k) for k in source_keys)
        http = PlexHTTPClient(self._client)

        try:
            http.put(f"/library/metadata/{target}/merge", params={"id": sources})
        except Exception as exc:
            return FixResult(key=target, action="merge", success=False, error=str(exc))

        return FixResult(
            key=target,
            action="merge",
            matched_to=f"Merged {len(source_keys)} items",
            success=True,
        )

    # --- Server info --------------------------------------------------------

    def server_info(self) -> ServerInfo:
        """Get server identity and version information.

        Returns:
            ServerInfo with machine ID, version, platform, etc.
        """
        http = PlexHTTPClient(self._client)
        data = http.get("/")

        if data is None:
            return ServerInfo()

        media_container = data.get("MediaContainer", data)
        return ServerInfo(
            machine_id=media_container.get("machineIdentifier", ""),
            version=media_container.get("version", ""),
            platform=media_container.get("platform", ""),
            platform_version=media_container.get("platformVersion", ""),
            server_name=media_container.get("friendlyName", ""),
            owner=media_container.get("myPlexUsername", ""),
            product=media_container.get("product", ""),
        )

    def list_preferences(self) -> list[ServerPreference]:
        """List all server preference settings.

        Returns:
            List of ServerPreference objects.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        data = http.get("/:/prefs")

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        setting_list = container.get("Setting", [])

        if isinstance(setting_list, dict):
            setting_list = [setting_list]

        prefs = [
            ServerPreference(
                id=setting.get("id", ""),
                label=setting.get("label", ""),
                value=setting.get("value", ""),
                type=setting.get("type", ""),
                default=setting.get("default", ""),
                summary=setting.get("summary", ""),
            )
            for setting in setting_list
        ]

        return prefs

    def set_preference(self, pref_id: str, value: str) -> FixResult:
        """Set a server preference value.

        Args:
            pref_id: Preference key name (use list_preferences to find).
            value: New value for the preference.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        try:
            http.put("/:/prefs", params={pref_id: value})
        except Exception as exc:
            return FixResult(key=pref_id, action="set-preference", success=False, error=str(exc))

        return FixResult(key=pref_id, action="set-preference", success=True)

    # --- Butler tasks -------------------------------------------------------

    def list_butler_tasks(self) -> list[ButlerTask]:
        """List all butler (background maintenance) tasks.

        Returns:
            List of ButlerTask objects.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)
        data = http.get("/butler")

        if data is None:
            return []

        container = data.get("MediaContainer", data)
        task_list = container.get("ButlerTask", [])

        if isinstance(task_list, dict):
            task_list = [task_list]

        tasks = [
            ButlerTask(
                id=str(task.get("key", task.get("id", ""))),
                name=task.get("name", ""),
                description=task.get("description", task.get("summary", "")),
                enabled=task.get("enabled", True),
                schedule=task.get("schedule", ""),
                last_run=task.get("lastRunAt"),
                next_run=task.get("nextRunAt"),
            )
            for task in task_list
        ]

        return tasks

    def run_butler_task(self, task_name: str) -> FixResult:
        """Run a butler task immediately.

        Args:
            task_name: Name/key of the butler task to run.

        Returns:
            FixResult indicating success or failure.
        """
        from plexctl.client import PlexHTTPClient

        http = PlexHTTPClient(self._client)

        try:
            http.post(f"/butler/{task_name}")
        except Exception as exc:
            return FixResult(key=task_name, action="butler-run", success=False, error=str(exc))

        return FixResult(key=task_name, action="butler-run", success=True)

    # --- Watch history ------------------------------------------------------

    def history(
        self,
        maxresults: int | None = None,
        mindate: datetime | None = None,
        rating_key: int | None = None,
        account_id: int | None = None,
        section_id: int | None = None,
    ) -> list[WatchHistoryEntry]:
        """Fetch watch history from the server.

        Args:
            maxresults: Maximum number of history entries to return.
            mindate: Only return items viewed after this datetime.
            rating_key: Filter to a specific rating key.
            account_id: Filter to a specific Plex account ID.
            section_id: Filter to a specific library section ID.

        Returns:
            List of WatchHistoryEntry items.
        """
        server = self._client.server
        kwargs: dict[str, Any] = {}
        if maxresults is not None:
            kwargs["maxresults"] = maxresults
        if mindate is not None:
            kwargs["mindate"] = mindate
        if rating_key is not None:
            kwargs["ratingKey"] = rating_key
        if account_id is not None:
            kwargs["accountID"] = account_id
        if section_id is not None:
            kwargs["librarySectionID"] = section_id

        results = server.history(**kwargs)  # type: ignore[no-untyped-call]

        if not results:
            return []

        entries: list[WatchHistoryEntry] = []
        for item in results:
            viewed_at_val = getattr(item, "viewedAt", None)
            viewed_at_str = (
                viewed_at_val.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(viewed_at_val, datetime)
                else str(viewed_at_val) if viewed_at_val is not None else None
            )
            entries.append(
                WatchHistoryEntry(
                    key=str(getattr(item, "ratingKey", "")),
                    title=getattr(item, "title", ""),
                    media_type=getattr(item, "type", ""),
                    year=(int(getattr(item, "year", 0)) if getattr(item, "year", None) else None),
                    viewed_at=viewed_at_str,
                    account_id=_safe_int(getattr(item, "accountID", None)),
                    device_id=_safe_int(getattr(item, "deviceID", None)),
                    parent_title=getattr(item, "parentTitle", None),
                    grandparent_title=getattr(item, "grandparentTitle", None),
                )
            )

        return entries

    def stop_session(self, session_key: str, reason: str = "") -> FixResult:
        """Stop an active playback session.

        Args:
            session_key: The session key to stop.
            reason: Optional reason for stopping the session.

        Returns:
            FixResult indicating success or failure.
        """
        server = self._client.server

        try:
            sessions = server.sessions()  # type: ignore[no-untyped-call]
        except Exception as exc:
            return FixResult(
                key=session_key,
                action="stop-session",
                success=False,
                error=f"Failed to list sessions: {exc}",
            )

        for session in sessions:
            if str(getattr(session, "sessionKey", "")) == str(session_key):
                try:
                    session.stop(reason=reason)
                except Exception as exc:
                    return FixResult(
                        key=session_key, action="stop-session", success=False, error=str(exc)
                    )
                return FixResult(key=session_key, action="stop-session", success=True)

        return FixResult(
            key=session_key,
            action="stop-session",
            success=False,
            error=f"No active session found with key {session_key}",
        )

    def set_progress(
        self, rating_key: str | int, time_ms: int, state: str = "stopped"
    ) -> FixResult:
        """Set playback progress for a media item.

        Args:
            rating_key: Plex rating key for the item.
            time_ms: Progress time in milliseconds.
            state: Playback state to set (default 'stopped').

        Returns:
            FixResult indicating success or failure.
        """
        server = self._client.server
        key = str(rating_key)

        try:
            item = server.fetchItem(int(key))  # type: ignore[no-untyped-call]
            item.updateProgress(time_ms, state)
        except Exception as exc:
            return FixResult(key=key, action="set-progress", success=False, error=str(exc))

        return FixResult(
            key=key, title=getattr(item, "title", None), action="set-progress", success=True
        )

    # --- On Deck / Recently Added / Continue Watching -----------------------

    def on_deck(self, section_key: int | None = None) -> list[MediaMetadata]:
        """Fetch On Deck items.

        Args:
            section_key: Optional section key to scope the query.

        Returns:
            List of MediaMetadata for items on deck.
        """
        server = self._client.server

        if section_key is not None:
            section = server.library.sectionByID(section_key)
            items = section.onDeck()
        else:
            items = server.library.onDeck()

        if not items:
            return []

        return [_plex_item_to_metadata(item) for item in items]

    def recently_added(
        self, section_key: int | None = None, maxresults: int = 50, libtype: str | None = None
    ) -> list[MediaMetadata]:
        """Fetch recently added items.

        Args:
            section_key: Optional section key to scope the query.
            maxresults: Maximum number of items to return.
            libtype: Optional library type filter (e.g. 'movie', 'episode').

        Returns:
            List of MediaMetadata for recently added items.
        """
        server = self._client.server

        if section_key is not None:
            section = server.library.sectionByID(section_key)
            kwargs: dict[str, Any] = {}
            if libtype:
                kwargs["libtype"] = libtype
            items = section.recentlyAdded(maxresults, **kwargs)
        else:
            items = server.library.recentlyAdded()

        if not items:
            return []

        return [_plex_item_to_metadata(item) for item in items]

    def continue_watching(self, section_key: int | None = None) -> list[MediaMetadata]:
        """Fetch Continue Watching items.

        Args:
            section_key: Optional section key to scope the query.

        Returns:
            List of MediaMetadata for items in continue watching.
        """
        server = self._client.server

        if section_key is not None:
            section = server.library.sectionByID(section_key)
            items = section.continueWatching()
        else:
            items = server.continueWatching()  # type: ignore[no-untyped-call]

        if not items:
            return []

        return [_plex_item_to_metadata(item) for item in items]

    # --- Transcode sessions -------------------------------------------------

    def transcode_sessions(self) -> list[TranscodeSessionInfo]:
        """List active transcode sessions.

        Returns:
            List of TranscodeSessionInfo objects.
        """
        server = self._client.server
        sessions = server.transcodeSessions()  # type: ignore[no-untyped-call]

        if not sessions:
            return []

        results: list[TranscodeSessionInfo] = []
        for session in sessions:
            # plexapi TranscodeSession attributes
            source = getattr(session, "source", None) or {}
            target = getattr(session, "target", None) or {}
            if isinstance(source, list):
                source = source[0] if source else {}
            if isinstance(target, list):
                target = target[0] if target else {}

            results.append(
                TranscodeSessionInfo(
                    key=str(getattr(session, "key", "")),
                    throttled=bool(getattr(session, "throttled", False)),
                    progress=float(getattr(session, "progress", 0.0)),
                    speed=float(getattr(session, "speed", 0.0)),
                    error=bool(getattr(session, "error", False)),
                    duration=_safe_int(getattr(session, "duration", 0)) or 0,
                    context=getattr(session, "context", ""),
                    source_video=getattr(source, "videoCodec", ""),
                    source_audio=getattr(source, "audioCodec", ""),
                    target_video=getattr(target, "videoCodec", ""),
                    target_audio=getattr(target, "audioCodec", ""),
                    video_decision=getattr(session, "videoDecision", ""),
                    audio_decision=getattr(session, "audioDecision", ""),
                    protocol=getattr(session, "protocol", ""),
                )
            )

        return results

    # --- Server management --------------------------------------------------

    def check_for_update(self) -> UpdateInfo | None:
        """Check for available Plex Media Server updates.

        Returns:
            UpdateInfo with version, added, fixed, download_url, state,
            and release_notes if an update is available, or None if
            already up to date.
        """
        server = self._client.server
        release = server.checkForUpdate(force=True)  # type: ignore[no-untyped-call]

        if release is None:
            return None

        return UpdateInfo(
            version=getattr(release, "version", ""),
            added=getattr(release, "added", ""),
            fixed=getattr(release, "fixed", ""),
            download_url=getattr(release, "downloadURL", ""),
            state=getattr(release, "state", ""),
            release_notes=getattr(release, "releaseNotes", ""),
        )

    def install_update(self) -> bool:
        """Install the latest available Plex Media Server update.

        Returns:
            True if update was applied, False if already up to date.
        """
        server = self._client.server
        release = server.checkForUpdate(force=True)  # type: ignore[no-untyped-call]

        if release is None:
            return False

        server.installUpdate()  # type: ignore[no-untyped-call]
        return True

    def bandwidth_stats(
        self,
        timespan: str = "hours",
        account_id: int | None = None,
        device_id: int | None = None,
        lan: bool | None = None,
    ) -> list[BandwidthStats]:
        """Get bandwidth statistics.

        Args:
            timespan: Time granularity ("seconds", "hours", "days", "weeks", "months").
            account_id: Filter by Plex account ID.
            device_id: Filter by device ID.
            lan: True for local traffic only, False for remote only.

        Returns:
            List of BandwidthStats entries.
        """
        server = self._client.server
        kwargs: dict[str, Any] = {"timespan": timespan}
        if account_id is not None:
            kwargs["accountID"] = account_id
        if device_id is not None:
            kwargs["deviceID"] = device_id
        if lan is not None:
            kwargs["lan"] = lan

        results = server.bandwidth(**kwargs)  # type: ignore[no-untyped-call]

        if not results:
            return []

        entries: list[BandwidthStats] = []
        for stat in results:
            at_val = getattr(stat, "at", None)
            at_str = (
                at_val.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(at_val, datetime)
                else str(at_val) if at_val is not None else ""
            )
            entries.append(
                BandwidthStats(
                    at=at_str,
                    bytes=getattr(stat, "bytes", 0),
                    lan=bool(getattr(stat, "lan", False)),
                    timespan=str(getattr(stat, "timespan", timespan)),
                    account_id=_safe_int(getattr(stat, "accountID", None)),
                    device_id=_safe_int(getattr(stat, "deviceID", None)),
                )
            )

        return entries

    def resource_stats(self) -> list[ResourceStats]:
        """Get server resource utilization statistics.

        Returns:
            List of ResourceStats entries with CPU and memory utilization.
        """
        server = self._client.server
        results = server.resources()  # type: ignore[no-untyped-call]

        if not results:
            return []

        entries: list[ResourceStats] = []
        for stat in results:
            at_val = getattr(stat, "at", None)
            at_str = (
                at_val.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(at_val, datetime)
                else str(at_val) if at_val is not None else ""
            )
            entries.append(
                ResourceStats(
                    at=at_str,
                    host_cpu=getattr(stat, "hostCpuUtilization", 0.0),
                    host_memory=getattr(stat, "hostMemoryUtilization", 0.0),
                    process_cpu=getattr(stat, "processCpuUtilization", 0.0),
                    process_memory=getattr(stat, "processMemoryUtilization", 0.0),
                    timespan=getattr(stat, "timespan", 6),
                )
            )

        return entries

    def download_logs(self, savepath: str | None = None, unpack: bool = False) -> str:
        """Download Plex Media Server logs.

        Args:
            savepath: Directory to save the logs zip. Defaults to cwd.
            unpack: Whether to unpack the zip after downloading.

        Returns:
            Path to the downloaded file.
        """
        server = self._client.server
        return str(server.downloadLogs(savepath=savepath, unpack=unpack))  # type: ignore[no-untyped-call]

    def download_databases(self, savepath: str | None = None, unpack: bool = False) -> str:
        """Download Plex Media Server databases for backup.

        Args:
            savepath: Directory to save the databases zip. Defaults to cwd.
            unpack: Whether to unpack the zip after downloading.

        Returns:
            Path to the downloaded file.
        """
        server = self._client.server
        return str(server.downloadDatabases(savepath=savepath, unpack=unpack))  # type: ignore[no-untyped-call]


# --- Helpers ----------------------------------------------------------------


def _safe_int(value: Any) -> int | None:
    """Safely convert a value to int, returning None for missing/empty values."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _first_str(data: dict[str, Any], key: str) -> str | None:
    """Extract a string from a dict that may contain a list value."""
    val = data.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        return str(val[0]) if val else None
    return str(val)


def _plex_item_to_metadata(item: Any) -> MediaMetadata:
    """Convert a plexapi media item to our MediaMetadata model.

    Works with any plexapi object that has ratingKey, title, type, and year.
    """
    return MediaMetadata(
        key=str(getattr(item, "ratingKey", "")),
        title=getattr(item, "title", None),
        year=int(item.year) if getattr(item, "year", None) else None,
        media_type=MediaType.from_plex_type(getattr(item, "type", "")),
    )


def parse_duration(duration_str: str) -> datetime:
    """Parse a relative duration string like '7d', '1h', '30m' into a datetime.

    Supported suffixes: d (days), h (hours), m (minutes), w (weeks).

    Args:
        duration_str: A string like '7d' or '1h'.

    Returns:
        A datetime representing (now - duration).

    Raises:
        ValueError: If the format is invalid.
    """
    match = re.match(r"^(\d+)([dhmw])$", duration_str.strip().lower())
    if not match:
        msg = (
            f"Invalid duration format: '{duration_str}'. "
            "Use a number followed by d (days), h (hours), m (minutes), or w (weeks)."
        )
        raise ValueError(msg)

    amount = int(match.group(1))
    unit = match.group(2)

    now = datetime.now(tz=UTC)

    delta_map: dict[str, timedelta] = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "m": timedelta(minutes=amount),
        "w": timedelta(weeks=amount),
    }

    return now - delta_map[unit]
