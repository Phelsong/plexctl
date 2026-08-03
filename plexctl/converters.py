"""Convert rich Pydantic models to flat CSV-exportable models.

Each converter takes source model(s) and produces flat row models suitable
for CSV serialization. Nested structures are flattened to pipe-separated
strings or dot-separated keys, making the data spreadsheet-friendly.
"""

from __future__ import annotations

from rich.table import Table

from plexctl.models import (
    AlbumInfo,
    ArtistInfo,
    BandwidthStats,
    ButlerTask,
    CollectionInfo,
    CollectionMetadata,
    CsvAlbumInfo,
    CsvArtistInfo,
    CsvBandwidthStats,
    CsvButlerTask,
    CsvCollectionInfo,
    CsvCollectionMetadata,
    CsvFsDir,
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
    CsvShowDiagnostics,
    CsvSimilarMedia,
    CsvSmartPlaylist,
    CsvSubtitleStreamInfo,
    CsvTrackInfo,
    CsvTranscodeSessionInfo,
    CsvTriageIssue,
    CsvUpdateInfo,
    CsvWatchHistoryEntry,
    FsDir,
    LibrarySection,
    MediaMetadata,
    MediaPartDetail,
    MediaTreeItem,
    PhotoAlbumInfo,
    PhotoInfo,
    PlaybackSession,
    Playlist,
    PlaylistItem,
    ResourceStats,
    SearchResult,
    SeasonGap,
    ServerInfo,
    ServerPreference,
    ShowDiagnostics,
    SimilarMedia,
    SmartPlaylist,
    SubtitleStreamInfo,
    TrackInfo,
    TranscodeSessionInfo,
    TriageIssue,
    UpdateInfo,
    UserAccount,
    WatchHistoryEntry,
)


def media_metadata_to_csv(item: MediaMetadata) -> CsvMediaMetadata:
    """Convert MediaMetadata to a flat CSV row."""
    return CsvMediaMetadata(
        key=item.key,
        title=item.title or "",
        media_type=item.media_type.value if item.media_type else "",
        year=str(item.year) if item.year else "",
        rating=f"{item.rating:.1f}" if item.rating else "",
        audience_rating=f"{item.audience_rating:.1f}" if item.audience_rating else "",
        content_rating=item.content_rating or "",
        studio=item.studio or "",
        summary=(item.summary or "").replace("\n", " ").strip(),
    )


def library_section_to_csv(section: LibrarySection) -> CsvLibrarySection:
    """Convert LibrarySection to a flat CSV row."""
    return CsvLibrarySection(
        key=section.key,
        title=section.title,
        section_type=section.section_type.value if section.section_type else "",
        agent=section.agent or "",
        scanner=section.scanner or "",
        language=section.language or "",
        count=str(section.count),
    )


def collection_info_to_csv(collection: CollectionInfo) -> CsvCollectionInfo:
    """Convert CollectionInfo to a flat CSV row."""
    return CsvCollectionInfo(
        key=collection.key,
        title=collection.title,
        smart=str(collection.smart),
        content_count=str(collection.content_count),
        section_title=collection.section_title or "",
    )


def show_diagnostics_to_csv(show: ShowDiagnostics) -> CsvShowDiagnostics:
    """Convert ShowDiagnostics to a flat CSV row."""
    return CsvShowDiagnostics(
        key=show.key,
        title=show.title or "",
        year=str(show.year) if show.year else "",
        locations="|".join(show.locations),
        total_episodes=str(show.total_episodes),
        unanalyzed_episodes=str(show.unanalyzed_episodes),
        multi_media_episodes=str(show.multi_media_episodes),
        missing_file_episodes=str(show.missing_file_episodes),
    )


def triage_issue_to_csv(issue: TriageIssue) -> CsvTriageIssue:
    """Convert TriageIssue to a flat CSV row."""
    return CsvTriageIssue(
        issue_type=issue.issue_type.value,
        severity=issue.severity.value,
        action=issue.action.value,
        plex_key=issue.plex_key or "",
        plex_title=issue.plex_title or "",
        shoko_id=str(issue.shoko_id) if issue.shoko_id else "",
        shoko_name=issue.shoko_name or "",
        detail=issue.detail,
        paths="|".join(issue.paths),
    )


def season_gap_to_csv(gap: SeasonGap) -> CsvSeasonGap:
    """Convert SeasonGap to a flat CSV row."""
    shoko_series = "|".join(
        f"{s.name}({s.episode_count}ep,AniDB:{s.anidb_id})" for s in gap.shoko_series
    )
    plex_seasons = "|".join(
        f"S{s.season_number:02d}:{s.title}({s.episode_count}ep)" for s in gap.plex_seasons
    )
    deficit = gap.expected_episode_count - gap.actual_episode_count

    return CsvSeasonGap(
        plex_title=gap.plex_title,
        plex_key=gap.plex_key or "",
        tmdb_show_id=str(gap.tmdb_show_id) if gap.tmdb_show_id else "",
        actual_episode_count=str(gap.actual_episode_count),
        expected_episode_count=str(gap.expected_episode_count),
        missing_episodes=str(deficit) if deficit > 0 else "0",
        is_missing=str(gap.is_missing),
        shoko_series=shoko_series,
        plex_seasons=plex_seasons,
    )


def fs_dir_to_csv(fs_dir: FsDir) -> CsvFsDir:
    """Convert FsDir to a flat CSV row."""
    return CsvFsDir(
        path=fs_dir.path,
        name=fs_dir.name,
        video_files=str(fs_dir.video_files),
        has_files=str(fs_dir.has_files),
        subdir_count=str(fs_dir.subdir_count),
        subdirs="|".join(fs_dir.subdirs),
        is_plex_location=str(fs_dir.is_plex_location),
        plex_shows="|".join(fs_dir.plex_shows),
    )


def media_part_detail_to_csv(detail: MediaPartDetail) -> CsvMediaPartDetail:
    """Convert MediaPartDetail to a flat CSV row."""
    return CsvMediaPartDetail(
        file_path=detail.file_path,
        size=str(detail.size) if detail.size else "",
        accessible=str(detail.accessible) if detail.accessible is not None else "",
        exists=str(detail.exists) if detail.exists is not None else "",
        video_codec=detail.video_codec or "",
        audio_codec=detail.audio_codec or "",
        container=detail.container or "",
        resolution=detail.resolution or "",
        bitrate=str(detail.bitrate) if detail.bitrate else "",
        duration=str(detail.duration) if detail.duration else "",
    )


def playback_session_to_csv(session: PlaybackSession) -> CsvPlaybackSession:
    """Convert PlaybackSession to a flat CSV row."""
    return CsvPlaybackSession(
        session_key=session.session_key,
        user=session.user,
        player_title=session.player_title,
        player_address=session.player_address,
        state=session.state,
        media_type=session.media_type,
        title=session.title,
        grandparent_title=session.grandparent_title or "",
        parent_title=session.parent_title or "",
        rating_key=session.rating_key,
        duration=str(session.duration) if session.duration else "",
        view_offset=str(session.view_offset) if session.view_offset else "",
        bitrate=str(session.bitrate) if session.bitrate else "",
        video_codec=session.video_codec or "",
        audio_codec=session.audio_codec or "",
        container=session.container or "",
        transcoding=str(session.transcoding),
    )


def server_preference_to_csv(pref: ServerPreference) -> CsvServerPreference:
    """Convert ServerPreference to a flat CSV row."""
    return CsvServerPreference(
        id=pref.id,
        label=pref.label,
        value=str(pref.value),
        type=pref.type,
        default=str(pref.default),
        summary=pref.summary,
    )


def server_info_to_csv(info: ServerInfo) -> CsvServerInfo:
    """Convert ServerInfo to a flat CSV row."""
    return CsvServerInfo(
        machine_id=info.machine_id,
        version=info.version,
        platform=info.platform,
        platform_version=info.platform_version,
        server_name=info.server_name,
        owner=info.owner,
        product=info.product,
    )


def user_account_to_table(user: UserAccount) -> Table:
    """Create a Rich Table from UserAccount for display.

    Args:
        user: UserAccount object to convert

    Returns:
        Rich Table object with user account information
    """
    table = Table(title="User Account Info", show_header=True, header_style="bold blue")
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="green")

    table.add_row("ID", str(user.id))
    table.add_row("Username", user.username)
    table.add_row("Email", user.email)
    table.add_row("Title", user.title)
    table.add_row("Friend", "Yes" if user.friend else "No")
    table.add_row("Restricted", "Yes" if user.restricted else "No")
    table.add_row("DoH", "Yes" if user.doh else "No")
    table.add_row("Anonymous", "Yes" if user.anonymous else "No")

    return table


def butler_task_to_csv(task: ButlerTask) -> CsvButlerTask:
    """Convert ButlerTask to a flat CSV row."""
    return CsvButlerTask(
        id=task.id,
        name=task.name,
        description=task.description,
        enabled=str(task.enabled),
        interval=str(task.interval),
        schedule_randomized=str(task.schedule_randomized),
        schedule=task.schedule,
    )


def media_tree_item_to_csv(item: MediaTreeItem) -> CsvMediaTreeItem:
    """Convert MediaTreeItem to a flat CSV row."""
    children_summary = "|".join(f"{c.title}({c.key})" for c in item.children)
    return CsvMediaTreeItem(
        key=item.key,
        title=item.title or "",
        media_type=item.media_type.value if item.media_type else "",
        year=str(item.year) if item.year else "",
        leaf_count=str(item.leaf_count) if item.leaf_count else "",
        viewed_leaf_count=str(item.viewed_leaf_count) if item.viewed_leaf_count else "",
        parent_key=item.parent_key or "",
        parent_title=item.parent_title or "",
        children=children_summary,
    )


def collection_metadata_to_csv(collection: CollectionMetadata) -> CsvCollectionMetadata:
    """Convert CollectionMetadata to a flat CSV row."""
    return CsvCollectionMetadata(
        key=collection.key,
        title=collection.title,
        smart=str(collection.smart),
        content_count=str(collection.content_count),
        section_key=collection.section_key or "",
        section_title=collection.section_title or "",
        summary=(collection.summary or "").replace("\n", " ").strip(),
        thumb=collection.thumb or "",
        art=collection.art or "",
        added_at=str(collection.added_at or ""),
        updated_at=str(collection.updated_at or ""),
    )


def search_result_to_csv(result: SearchResult) -> CsvSearchResult:
    """Convert SearchResult to a flat CSV row."""
    return CsvSearchResult(
        key=result.key,
        title=result.title,
        media_type=result.media_type.value if result.media_type else "",
        year=str(result.year) if result.year else "",
        summary=(result.summary or "").replace("\n", " ").strip(),
        rating=f"{result.rating:.1f}" if result.rating else "",
        thumb=result.thumb or "",
        section_key=result.section_key or "",
        section_title=result.section_title or "",
    )


def similar_media_to_csv(media: SimilarMedia) -> CsvSimilarMedia:
    """Convert SimilarMedia to a flat CSV row."""
    return CsvSimilarMedia(
        key=media.key,
        title=media.title,
        media_type=media.media_type.value if media.media_type else "",
        year=str(media.year) if media.year else "",
        similarity=str(media.similarity) if media.similarity is not None else "",
        thumb=media.thumb or "",
    )


def smart_playlist_to_csv(playlist: SmartPlaylist) -> CsvSmartPlaylist:
    """Convert SmartPlaylist to a flat CSV row."""
    filters_summary = "|".join(f"{f.field}{f.operator}{f.value}" for f in playlist.filters)
    return CsvSmartPlaylist(
        key=playlist.key,
        title=playlist.title,
        playlist_type=playlist.playlist_type.value if playlist.playlist_type else "",
        smart=str(playlist.smart),
        item_count=str(playlist.item_count),
        composite=playlist.composite or "",
        added_at=str(playlist.added_at or ""),
        updated_at=str(playlist.updated_at or ""),
        filters=filters_summary,
    )


def playlist_item_to_csv(item: PlaylistItem) -> CsvPlaylistItem:
    """Convert PlaylistItem to a flat CSV row."""
    return CsvPlaylistItem(
        key=item.key,
        title=item.title,
        media_type=item.media_type.value if item.media_type else "",
        year=str(item.year) if item.year else "",
        duration=str(item.duration) if item.duration else "",
        thumb=item.thumb or "",
    )


def playlist_to_csv(playlist: Playlist) -> CsvPlaylist:
    """Convert Playlist to a flat CSV row."""
    return CsvPlaylist(
        key=playlist.key,
        title=playlist.title,
        playlist_type=playlist.playlist_type.value if playlist.playlist_type else "",
        smart=str(playlist.smart),
        item_count=str(playlist.item_count),
        composite=playlist.composite or "",
        added_at=str(playlist.added_at or ""),
        updated_at=str(playlist.updated_at or ""),
    )


def watch_history_entry_to_csv(entry: WatchHistoryEntry) -> CsvWatchHistoryEntry:
    """Convert WatchHistoryEntry to a flat CSV row."""
    return CsvWatchHistoryEntry(
        key=entry.key,
        title=entry.title,
        media_type=entry.media_type,
        year=str(entry.year) if entry.year else "",
        viewed_at=entry.viewed_at or "",
        account_id=str(entry.account_id) if entry.account_id else "",
        device_id=str(entry.device_id) if entry.device_id else "",
        parent_title=entry.parent_title or "",
        grandparent_title=entry.grandparent_title or "",
    )


def transcode_session_to_csv(session: TranscodeSessionInfo) -> CsvTranscodeSessionInfo:
    """Convert TranscodeSessionInfo to a flat CSV row."""
    return CsvTranscodeSessionInfo(
        key=session.key,
        throttled=str(session.throttled),
        progress=str(session.progress),
        speed=str(session.speed),
        error=str(session.error),
        duration=str(session.duration),
        context=session.context,
        source_video=session.source_video,
        source_audio=session.source_audio,
        target_video=session.target_video,
        target_audio=session.target_audio,
        video_decision=session.video_decision,
        audio_decision=session.audio_decision,
        protocol=session.protocol,
    )


def artist_info_to_csv(artist: ArtistInfo) -> CsvArtistInfo:
    """Convert ArtistInfo to a flat CSV row."""
    return CsvArtistInfo(
        key=artist.key,
        title=artist.title or "",
        sort_title=artist.sort_title or "",
        summary=(artist.summary or "").replace("\n", " ").strip(),
        thumb=artist.thumb or "",
        art=artist.art or "",
        genre=artist.genre or "",
        country=artist.country or "",
        album_count=str(artist.album_count),
        rating=f"{artist.rating:.1f}" if artist.rating else "",
        user_rating=f"{artist.user_rating:.1f}" if artist.user_rating else "",
    )


def album_info_to_csv(album: AlbumInfo) -> CsvAlbumInfo:
    """Convert AlbumInfo to a flat CSV row."""
    return CsvAlbumInfo(
        key=album.key,
        title=album.title or "",
        sort_title=album.sort_title or "",
        artist=album.artist or "",
        artist_key=album.artist_key or "",
        year=str(album.year) if album.year else "",
        summary=(album.summary or "").replace("\n", " ").strip(),
        thumb=album.thumb or "",
        genre=album.genre or "",
        studio=album.studio or "",
        track_count=str(album.track_count),
        rating=f"{album.rating:.1f}" if album.rating else "",
        user_rating=f"{album.user_rating:.1f}" if album.user_rating else "",
        originally_available=album.originally_available or "",
    )


def track_info_to_csv(track: TrackInfo) -> CsvTrackInfo:
    """Convert TrackInfo to a flat CSV row."""
    return CsvTrackInfo(
        key=track.key,
        title=track.title or "",
        sort_title=track.sort_title or "",
        artist=track.artist or "",
        artist_key=track.artist_key or "",
        album=track.album or "",
        album_key=track.album_key or "",
        track_number=str(track.track_number) if track.track_number else "",
        disc_number=str(track.disc_number) if track.disc_number else "",
        duration=str(track.duration) if track.duration else "",
        year=str(track.year) if track.year else "",
        genre=track.genre or "",
        rating=f"{track.rating:.1f}" if track.rating else "",
        user_rating=f"{track.user_rating:.1f}" if track.user_rating else "",
        view_count=str(track.view_count),
        media_type=track.media_type,
    )


def photo_album_to_csv(album: PhotoAlbumInfo) -> CsvPhotoAlbumInfo:
    """Convert PhotoAlbumInfo to a flat CSV row."""
    return CsvPhotoAlbumInfo(
        key=album.key,
        title=album.title,
        sort_title=album.sort_title or "",
        summary=(album.summary or "").replace("\n", " ").strip(),
        thumb=album.thumb or "",
        photo_count=str(album.photo_count),
        user_rating=f"{album.user_rating:.1f}" if album.user_rating else "",
    )


def photo_info_to_csv(photo: PhotoInfo) -> CsvPhotoInfo:
    """Convert PhotoInfo to a flat CSV row."""
    return CsvPhotoInfo(
        key=photo.key,
        title=photo.title,
        sort_title=photo.sort_title or "",
        album=photo.album or "",
        album_key=photo.album_key or "",
        originally_available=photo.originally_available or "",
        thumb=photo.thumb or "",
        user_rating=f"{photo.user_rating:.1f}" if photo.user_rating else "",
        media_type=photo.media_type,
        year=str(photo.year) if photo.year else "",
        tags=photo.tags or "",
    )


def subtitle_stream_to_csv(stream: SubtitleStreamInfo) -> CsvSubtitleStreamInfo:
    """Convert SubtitleStreamInfo to a flat CSV row."""
    return CsvSubtitleStreamInfo(
        id=str(stream.id),
        language=stream.language,
        language_code=stream.language_code,
        language_tag=stream.language_tag,
        title=stream.title,
        display_title=stream.display_title,
        extended_display_title=stream.extended_display_title,
        codec=stream.codec,
        format=stream.format,
        forced=str(stream.forced),
        hearing_impaired=str(stream.hearing_impaired),
        score=str(stream.score) if stream.score is not None else "",
        provider=stream.provider,
        key=stream.key,
        selected=str(stream.selected),
        can_auto_sync=str(stream.can_auto_sync),
        perfect_match=str(stream.perfect_match),
        user_id=str(stream.user_id) if stream.user_id is not None else "",
    )


def update_info_to_csv(info: UpdateInfo) -> CsvUpdateInfo:
    """Convert UpdateInfo to a flat CSV row."""
    return CsvUpdateInfo(
        version=info.version,
        added=info.added,
        fixed=info.fixed,
        download_url=info.download_url,
        state=info.state,
        release_notes=info.release_notes,
    )


def bandwidth_stats_to_csv(stat: BandwidthStats) -> CsvBandwidthStats:
    """Convert BandwidthStats to a flat CSV row."""
    return CsvBandwidthStats(
        at=stat.at,
        bytes=str(stat.bytes),
        lan=str(stat.lan),
        timespan=str(stat.timespan),
        account_id=str(stat.account_id) if stat.account_id is not None else "",
        device_id=str(stat.device_id) if stat.device_id is not None else "",
    )


def resource_stats_to_csv(stat: ResourceStats) -> CsvResourceStats:
    """Convert ResourceStats to a flat CSV row."""
    return CsvResourceStats(
        at=stat.at,
        host_cpu=str(stat.host_cpu),
        host_memory=str(stat.host_memory),
        process_cpu=str(stat.process_cpu),
        process_memory=str(stat.process_memory),
        timespan=str(stat.timespan),
    )
