"""Pydantic models for Plex metadata.

These models define the shape of data we read from and write to Plex,
providing typed boundaries between raw plexapi objects and our domain logic.
"""

from __future__ import annotations

import contextlib
from datetime import datetime  # noqa: TC003
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from plexapi.audio import Audio
    from plexapi.collection import Collection
    from plexapi.photo import Photo
    from plexapi.playlist import Playlist as Plex_Playlist
    from plexapi.video import Video


class MediaType(StrEnum):
    """Supported Plex media types."""

    MOVIE = "movie"
    SHOW = "show"
    SEASON = "season"
    EPISODE = "episode"
    ARTIST = "artist"
    ALBUM = "album"
    TRACK = "track"
    COLLECTION = "collection"
    PLAYLIST = "playlist"
    MEDIATAG = "mediaTag"
    # List of Metadata Subtypes
    PHOTO = "photo"
    PODCAST = "podcast"
    WEBSHOW = "webshow"
    NEWS = "news"
    # Collection Subtypes
    # movie
    # show
    # artist
    # album
    # Extras Subtypes
    TRAILER = "trailer"
    # deletedScene
    INTERVIEW = "interview"
    MUSICVIDEO = "musicVideo"
    # behindTheScenes
    # sceneOrSample
    # liveMusicVideo
    # lyricMusicVideo
    CONCERT = "concert"
    # featurette
    SHORT = "short"
    # other

    @classmethod
    def from_plex_type(cls, value: str) -> MediaType | None:
        """Convert a plexapi section type string to a MediaType.

        Returns None for types not in the enum (e.g. unknown future types).
        """
        try:
            return cls(value)
        except ValueError:
            return None


class MetadataType(IntEnum):
    movie = 1
    show = 2
    season = 3
    episode = 4
    trailer = 5
    person = 7
    artist = 8
    album = 9
    track = 0
    clip = 12
    photo = 13
    photoalbum = 14
    playlist = 15
    playlistfolder = 16
    collection = 18

    # def __getitem__(self, key):
    #     self[key], self[key].value


def plex_media_types() -> tuple[type[object], ...]:
    """Return the tuple of plexapi media types for isinstance checks.

    Imported lazily to avoid loading plexapi (and its transitive deps:
    requests/urllib3/httpx) at import time. Cached after first call.
    """
    from plexapi.audio import Audio
    from plexapi.collection import Collection
    from plexapi.photo import Photo
    from plexapi.playlist import Playlist
    from plexapi.video import Video

    types = (Video, Audio, Photo, Collection, Playlist)
    plex_media_types.__wrapped__ = types  # type: ignore[attr-defined]
    return types


if TYPE_CHECKING:
    PLEX_MEDIA = Video | Audio | Photo | Collection | Plex_Playlist
# | Tag


class MetadataEdit(BaseModel):
    """A single metadata field edit operation.

    Attributes:
        field: The Plex field name (e.g. 'title', 'summary', 'year').
        value: The new value to set.
    """

    field: str
    value: str | int | float | None


class MediaMetadata(BaseModel):
    """Core metadata for a Plex media item.

    This is the canonical shaped data we work with internally.
    All fields are optional to support partial updates.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title.
        original_title: Original language title.
        sort_title: Title used for sorting.
        summary: Description / plot summary.
        year: Release year.
        originally_available: Original release/air date.
        rating: Audience rating (0-10).
        audience_rating: Audience rating (0-10).
        content_rating: Content rating (e.g. 'PG-13', 'TV-MA').
        studio: Studio / network name.
        tagline: Promotional tagline.
        media_type: Type of media item.
    """

    key: str
    title: str | None = None
    original_title: str | None = None
    sort_title: str | None = None
    summary: str | None = None
    year: int | None = None
    originally_available: datetime | None = None
    rating: float | None = None
    audience_rating: float | None = None
    content_rating: str | None = None
    studio: str | None = None
    tagline: str | None = None
    media_type: MediaType | None = None


class CollectionInfo(BaseModel):
    """Metadata about a Plex collection.

    Attributes:
        key: Collection rating key.
        title: Collection name.
        smart: Whether this is a smart collection.
        content_count: Number of items in the collection.
        section_title: Library section this collection belongs to.
    """

    key: str
    title: str
    smart: bool = False
    content_count: int = 0
    section_title: str | None = None


class LibrarySection(BaseModel):
    """A Plex library section (e.g. Movies, TV Shows).

    Attributes:
        key: Section key.
        title: Section name.
        section_type: Type of content (movie, show, artist, etc.).
        agent: Metadata agent used by this section.
        scanner: Scanner used by this section.
        language: Language of this section.
        count: Number of items in the section.
    """

    key: str
    title: str
    section_type: MediaType | None = None
    agent: str | None = None
    scanner: str | None = None
    language: str | None = None
    count: int = 0


class LibraryLocation(BaseModel):
    """A filesystem location for a Plex library section.

    Plex sections scan one or more directories for media. Each location
    maps to a path on disk that Ples uses to find content.

    Attributes:
        id: Location ID.
        path: Filesystem path scanned by this section.
    """

    id: int
    path: str


class MediaTreeItem(BaseModel):
    """A single item in a hierarchical media tree.

    Represents a show, season, episode, or movie depending on context.
    Used to build tree views of library content.

    Attributes:
        key: Plex rating key.
        title: Display title.
        media_type: Type of media (show, season, episode, movie).
        year: Release year (for shows/movies).
        leaf_count: Total leaf items (episodes for shows, tracks for albums).
        viewed_leaf_count: Number of viewed leaf items.
        parent_key: Rating key of the parent item (for seasons/episodes).
        parent_title: Title of the parent (e.g. show name for a season).
        children: Nested child items (seasons for shows, episodes for seasons).
    """

    key: str
    title: str | None = None
    media_type: MediaType | None = None
    year: int | None = None
    leaf_count: int | None = None
    viewed_leaf_count: int | None = None
    parent_key: str | None = None
    parent_title: str | None = None
    children: list[MediaTreeItem] = Field(default_factory=list)


class CollectionMetadata(BaseModel):
    """Detailed metadata about a Plex collection.

    Extends CollectionInfo with additional fields available when
    fetching a single collection by key.

    Attributes:
        key: Collection rating key.
        title: Collection name.
        smart: Whether this is a smart collection.
        content_count: Number of items in the collection.
        section_key: Library section key this collection belongs to.
        section_title: Library section name this collection belongs to.
        summary: Collection description.
        thumb: URL path to thumbnail/poster image.
        art: URL path to background art image.
        added_at: When the collection was created.
        updated_at: When the collection was last updated.
    """

    key: str
    title: str
    smart: bool = False
    content_count: int = 0
    section_key: str | None = None
    section_title: str | None = None
    summary: str | None = None
    thumb: str | None = None
    art: str | None = None
    added_at: int | str | None = None
    updated_at: int | str | None = None


# --- Diagnostic models ---------------------------------------------------


class MediaPartDetail(BaseModel):
    """Detailed information about a single file within a media item.

    Plex episodes can have multiple Media objects (different versions),
    each containing one or more MediaPart (files). This model captures
    the file-level details needed to diagnose parsing problems.

    Attributes:
        file_path: Full filesystem path to the media file.
        size: File size in bytes.
        accessible: Whether Plex can access the file.
        exists: Whether the file exists on disk.
        video_codec: Detected video codec (e.g. 'h264', 'hevc').
        audio_codec: Detected audio codec (e.g. 'aac', 'ac3').
        container: File container format (e.g. 'mp4', 'mkv').
        resolution: Video resolution label (e.g. '720', '1080', '4k').
        bitrate: Stream bitrate.
        duration: Duration in milliseconds.
    """

    file_path: str
    size: int | None = None
    accessible: bool | None = None
    exists: bool | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    container: str | None = None
    resolution: str | None = None
    bitrate: int | None = None
    duration: int | None = None


class EpisodeDiagnostics(BaseModel):
    """Diagnostic information about a single episode's media state.

    Flags common problems:
    - Unanalyzed media (no codec/container info)
    - Multiple media versions (cross-season merges)
    - Missing or inaccessible files

    Attributes:
        key: Plex rating key.
        title: Episode title (e.g. 'Episode 1').
        sort_title: Sort title for ordering.
        season_number: Season this episode belongs to.
        episode_number: Episode number within the season.
        media_count: Number of Media objects (versions) for this episode.
        has_unanalyzed: True if any media lacks codec info.
        file_details: Details for each file across all media versions.
    """

    key: str
    title: str | None = None
    sort_title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    media_count: int = 0
    has_unanalyzed: bool = False
    file_details: list[MediaPartDetail] = Field(default_factory=list)


class ShowDiagnostics(BaseModel):
    """Diagnostic information about a TV show's file parsing state.

    Aggregates episode-level problems to surface shows that need attention.

    Attributes:
        key: Plex rating key.
        title: Show title.
        year: Release year.
        locations: List of filesystem paths Plex uses for this show.
        total_episodes: Total episodes in the show.
        unanalyzed_episodes: Episodes with no codec info.
        multi_media_episodes: Episodes with multiple media versions.
        missing_file_episodes: Episodes with inaccessible or missing files.
        episode_details: Per-episode diagnostics (only populated for deep scans).
    """

    key: str
    title: str | None = None
    year: int | None = None
    locations: list[str] = Field(default_factory=list)
    total_episodes: int = 0
    unanalyzed_episodes: int = 0
    multi_media_episodes: int = 0
    missing_file_episodes: int = 0
    episode_details: list[EpisodeDiagnostics] = Field(default_factory=list)


class SectionDiagnostics(BaseModel):
    """Aggregate diagnostic summary for a library section.

    Attributes:
        key: Section key.
        title: Section name.
        section_type: Type of content (e.g. show, movie).
        scanner: Scanner name used by this section.
        agent: Metadata agent for this section.
        section_locations: Filesystem paths for the section.
        total_shows: Total shows in the section.
        shows_with_issues: Number of shows that have problems.
        shows: Per-show diagnostics (only populated for deep scans).
    """

    key: str
    title: str
    section_type: MediaType | None = None
    scanner: str | None = None
    agent: str | None = None
    section_locations: list[str] = Field(default_factory=list)
    total_shows: int = 0
    shows_with_issues: int = 0
    shows: list[ShowDiagnostics] = Field(default_factory=list)


# --- Match/fix models ---------------------------------------------------


class MatchResult(BaseModel):
    """A metadata match result from Plex.

    When fixing incorrect matches, Plex returns search results
    with a name, score, year, and GUID identifying the match.

    Attributes:
        name: Title of the matched item.
        score: Match confidence score (higher is better).
        year: Release year of the matched item.
        guid: Plex GUID identifying the match source.
    """

    name: str
    score: int | None = None
    year: str | None = None
    guid: str | None = None


class FixResult(BaseModel):
    """Result from a match fix or unmatch operation.

    Attributes:
        key: Rating key of the item that was fixed.
        title: Title of the item after the operation.
        action: The action performed (e.g. 'fix-match', 'unmatch', 'refresh').
        matched_to: For fix-match, the name of the match applied.
        success: Whether the operation completed without error.
        error: Error message if the operation failed.
    """

    key: str
    title: str | None = None
    action: str = ""
    matched_to: str | None = None
    success: bool = True
    error: str | None = None


class BatchFixResult(BaseModel):
    """Result from a batch fix operation targeting multiple items.

    Tracks how many items were targeted, how many succeeded, and
    collects individual failures for review.

    Attributes:
        total: Total items targeted for the batch operation.
        succeeded: Items that completed successfully.
        failed: Items that failed.
        results: Per-item results for failures (only populated on failure).
    """

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[FixResult] = Field(default_factory=list)


# --- Filesystem comparison models ----------------------------------------


VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mkv",
        ".mp4",
        ".avi",
        ".wmv",
        ".flv",
        ".mov",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".ts",
        ".m2ts",
        ".webm",
        ".ogm",
    }
)


class FsDir(BaseModel):
    """A filesystem directory entry with video file counts.

    Represents a directory found under the section root path, with
    video file counts at this level and in subdirectories.

    Attributes:
        path: Full filesystem path.
        name: Directory name (last component of path).
        video_files: Number of video files directly in this directory.
        has_files: Whether this directory contains any regular files.
            Faster than counting; used for grouping risk detection
            when count_files is False.
        subdir_count: Number of subdirectories.
        subdirs: Names of immediate subdirectories.
        is_plex_location: Whether this path matches a known Plex show location.
        plex_shows: Plex show titles that reference this directory.
    """

    path: str
    name: str
    video_files: int = 0
    has_files: bool = False
    subdir_count: int = 0
    subdirs: list[str] = Field(default_factory=list)
    is_plex_location: bool = False
    plex_shows: list[str] = Field(default_factory=list)


class FsCompareResult(BaseModel):
    """Result of comparing a filesystem directory with Plex's view.

    Surfaces mismatches between what's on disk and what Plex knows about,
    helping identify files that ShokoRelay couldn't match, grouping issues,
    or directories Plex isn't tracking.

    Attributes:
        section_root: Root path of the library section (e.g. '/mnt/nfs/media/anime').
        section_title: Name of the Plex library section.
        scanner: Scanner name used by this section.
        total_dirs: Total directories found on filesystem.
        plex_tracked_dirs: Directories that match a Plex show location.
        orphan_dirs: Directories on disk not tracked by any Plex show.
        multi_location_shows: Plex shows with multiple filesystem locations.
        grouped_dirs: Directories with files and subdirs (ShokoRelay grouping risk).
    """

    section_root: str
    section_title: str
    scanner: str | None = None
    total_dirs: int = 0
    plex_tracked_dirs: int = 0
    orphan_dirs: list[FsDir] = Field(default_factory=list)
    multi_location_shows: list[tuple[str, list[str]]] = Field(default_factory=list)
    grouped_dirs: list[FsDir] = Field(default_factory=list)


class ReorgAction(BaseModel):
    """A single proposed filesystem reorganization action.

    Attributes:
        action: Type of action ('move', 'remove_files', 'flatten').
        source: Current path of the item.
        destination: Proposed destination path (for moves).
        reason: Why this action is recommended.
        risk: Risk level ('low', 'medium', 'high').
    """

    action: str
    source: str
    destination: str | None = None
    reason: str
    risk: str = "medium"


class ReorganizePlan(BaseModel):
    """Proposed filesystem restructuring to fix Plex parsing issues.

    Combines diagnostics and filesystem analysis into actionable
    recommendations that can be reviewed before execution.

    Attributes:
        section_title: Library section name.
        total_actions: Total proposed actions.
        actions: List of proposed reorganization actions.
        summary: Human-readable summary of the plan.
    """

    section_title: str
    total_actions: int = 0
    actions: list[ReorgAction] = Field(default_factory=list)
    summary: str = ""


# --- Shoko models -------------------------------------------------------


class ShokoSeriesIDs(BaseModel):
    """Identity cross-references for a Shoko series.

    Attributes:
        id: Shoko internal ID.
        anidb: AniDB ID.
        tmdb_show: TMDB TV show IDs (may be multiple for series with reboots).
        tmdb_movie: TMDB movie IDs.
        tvdb: TvDB IDs.
        imdb: IMDb IDs.
    """

    id: int
    anidb: int | None = None
    tmdb_show: list[int] = Field(default_factory=list)
    tmdb_movie: list[int] = Field(default_factory=list)
    tvdb: list[int] = Field(default_factory=list)
    imdb: list[str] = Field(default_factory=list)


class ShokoSeriesSizes(BaseModel):
    """Episode counts by type for a Shoko series.

    Attributes:
        episodes: Regular episodes.
        specials: Special episodes (S0).
        credits: Credits/opening sequences.
        trailers: Trailer episodes.
        parodies: Parody episodes.
        others: Episodes that don't fit other categories.
        unknown: Episodes with unclassified type.
    """

    episodes: int = 0
    specials: int = 0
    credits: int = 0
    trailers: int = 0
    parodies: int = 0
    others: int = 0
    unknown: int = 0


class ShokoSeries(BaseModel):
    """A series from Shoko Server.

    Represents an anime series with cross-references to multiple
    metadata providers (AniDB, TMDB, TvDB, IMDb).

    Attributes:
        ids: Cross-reference IDs.
        name: Series title.
        description: Series description/summary.
        episode_count: Total episodes across all types.
        local_sizes: Episode counts by type available locally.
        total_sizes: Total episode counts by type (local + missing).
    """

    ids: ShokoSeriesIDs
    name: str
    description: str | None = None
    episode_count: int = 0
    local_sizes: ShokoSeriesSizes = Field(default_factory=ShokoSeriesSizes)
    total_sizes: ShokoSeriesSizes = Field(default_factory=ShokoSeriesSizes)


class ShokoEpisodeType(StrEnum):
    """Episode type classification in Shoko/AniDB."""

    EPISODE = "episode"
    SPECIAL = "special"
    CREDIT = "credit"
    TRAILER = "trailer"
    PARODY = "parody"
    OTHER = "other"
    UNKNOWN = "unknown"

    @classmethod
    def from_anidb_type(cls, type_id: int) -> ShokoEpisodeType:
        """Convert AniDB numeric type to ShokoEpisodeType.

        AniDB types: 1=Episode, 2=Special, 3=Credit, 4=Trailer,
        5=Parody, 6=Other, 0=Unknown.
        """
        mapping = {
            1: cls.EPISODE,
            2: cls.SPECIAL,
            3: cls.CREDIT,
            4: cls.TRAILER,
            5: cls.PARODY,
            6: cls.OTHER,
        }
        return mapping.get(type_id, cls.UNKNOWN)

    @classmethod
    def from_api_type(cls, api_type: int | str) -> ShokoEpisodeType:
        """Convert a Shoko API episode type to ShokoEpisodeType.

        The Shoko API returns type as a string name (e.g. "Episode")
        when includeDataFrom=AniDB is used, or as a numeric ID otherwise.
        """
        if isinstance(api_type, str):
            try:
                return cls(api_type.lower())
            except ValueError:
                return cls.UNKNOWN
        return cls.from_anidb_type(api_type)


class ShokoEpisode(BaseModel):
    """An episode from Shoko Server.

    Combines AniDB episode data with TMDB season/episode mapping.

    Attributes:
        id: Shoko internal episode ID.
        name: Episode title.
        episode_number: Episode number within its type (from AniDB).
        episode_type: Classification (episode, special, credit, etc).
        season_number: TMDB season number (None for non-episodes).
        tmdb_episode_number: TMDB absolute episode number within the season.
            Only set when TMDB cross-reference data is available.
        tmdb_episode_id: TMDB episode ID for cross-ordering lookups.
            This ID is consistent across all TMDB episode orderings for
            the same show, making it the join key for mapping episodes
            to alternate season structures.
        anidb_id: AniDB episode ID.
        is_hidden: Whether the episode is hidden from normal view.
    """

    id: int
    name: str | None = None
    episode_number: int | None = None
    episode_type: ShokoEpisodeType = ShokoEpisodeType.UNKNOWN
    season_number: int | None = None
    tmdb_episode_number: int | None = None
    tmdb_episode_id: int | None = None
    anidb_id: int | None = None
    is_hidden: bool = False


class ShokoFileLocation(BaseModel):
    """A file location within Shoko's managed folders.

    Attributes:
        relative_path: Path relative to the managed folder root.
        is_accessible: Whether the file is currently accessible.
        managed_folder_id: ID of the managed folder containing this file.
    """

    relative_path: str
    is_accessible: bool = True
    managed_folder_id: int | None = None


class ShokoFile(BaseModel):
    """A video file tracked by Shoko Server.

    Every file in Shoko is linked to one series and one or more episodes.
    This model captures the file identity and its cross-references.

    Attributes:
        id: Shoko internal file ID.
        filename: Just the filename (not the full path).
        relative_path: Full path relative to the managed folder root.
        is_accessible: Whether the file is currently accessible.
        series_id: Shoko series ID this file belongs to.
        series_name: Name of the series this file belongs to.
        episode_ids: Shoko episode IDs this file is linked to.
        is_variation: Whether this is an alternate version.
        is_ignored: Whether this file is marked as ignored.
        resolution: Video resolution label (e.g. '1080p', '720p').
        duration: Duration in milliseconds.
    """

    id: int
    filename: str | None = None
    relative_path: str | None = None
    is_accessible: bool = True
    series_id: int | None = None
    series_name: str | None = None
    episode_ids: list[int] = Field(default_factory=list)
    is_variation: bool = False
    is_ignored: bool = False
    resolution: str | None = None
    duration: int | None = None
    crc32: str | None = None
    ed2k: str | None = None
    sha1: str | None = None


class ShokoGroup(BaseModel):
    """A Shoko group that contains related series.

    Groups organize series that share a franchise (e.g. all
    Arifureta series grouped together).

    Attributes:
        id: Shoko internal group ID.
        name: Group name.
        series_count: Number of series in this group.
        series_ids: IDs of series belonging to this group.
    """

    id: int
    name: str
    series_count: int = 0
    series_ids: list[int] = Field(default_factory=list)


class ShokoMismatch(BaseModel):
    """A detected mismatch between Shoko and Plex data.

    Surfaces files, series, or episodes that are linked in Shoko
    but appear problematic in Plex (e.g. missing metadata, wrong
    season mapping, inaccessible files).

    Attributes:
        mismatch_type: Category of the mismatch.
        shoko_id: Shoko internal ID (series, episode, or file).
        plex_key: Corresponding Plex rating key, if any.
        name: Human-readable name of the affected item.
        detail: Human-readable explanation of the problem.
        severity: How serious this mismatch is ('info', 'warning', 'error').
    """

    mismatch_type: str
    shoko_id: int | None = None
    plex_key: str | None = None
    name: str | None = None
    detail: str
    severity: str = "warning"


# --- TMDB link models -------------------------------------------------------


class TmdbSearchResult(BaseModel):
    """A TMDB search result from Shoko's online search.

    Represents a show or movie found by searching TMDB via Shoko's API.

    Attributes:
        id: TMDB ID of the show/movie.
        name: Title of the show/movie.
        overview: Short description.
        year: Release year or first aired year.
        first_aired: First aired date string.
        poster_url: URL to the poster image.
    """

    id: int
    name: str
    overview: str | None = None
    year: int | None = None
    first_aired: str | None = None
    poster_url: str | None = None


class TmdbLinkResult(BaseModel):
    """Result from a TMDB link/unlink operation on a Shoko series.

    Attributes:
        series_id: Shoko series ID that was modified.
        tmdb_id: TMDB show/movie ID that was linked or unlinked.
        action: Action performed ('linked' or 'unlinked').
        success: Whether the operation completed without error.
        error: Error message if the operation failed.
    """

    series_id: int
    tmdb_id: int | None = None
    action: str = ""
    success: bool = True
    error: str | None = None


# --- Triage models -------------------------------------------------------


class TriageIssueType(StrEnum):
    """Classification of triage issues."""

    UNANALYZED = "unanalyzed"
    MULTI_MEDIA = "multi_media"
    MISSING_FILES = "missing_files"
    NO_TMDB_LINK = "no_tmdb_link"
    NO_LOCAL_EPISODES = "no_local_episodes"
    MULTIPLE_TMDB_LINKS = "multiple_tmdb_links"
    GROUPING_RISK = "grouping_risk"
    ORPHAN_DIR = "orphan_dir"
    MULTI_LOCATION = "multi_location"


class TriageSeverity(StrEnum):
    """Severity levels for triage issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TriageAction(StrEnum):
    """Recommended fix actions for triage issues."""

    ANALYZE = "analyze"
    REFRESH = "refresh"
    FIX_MATCH = "fix-match"
    LINK_TMDB = "link-tmdb"
    REVIEW = "review"
    REORGANIZE = "reorganize"
    SHOKO_CONFIG = "shoko-config"


class TriageIssue(BaseModel):
    """A single triage issue combining data from Plex, Shoko, and filesystem.

    Attributes:
        issue_type: Classification of the issue.
        severity: How serious the issue is.
        action: Recommended fix action.
        plex_key: Plex rating key of the affected show (if applicable).
        plex_title: Title of the show in Plex.
        shoko_id: Shoko series ID (if applicable).
        shoko_name: Name of the series in Shoko.
        detail: Human-readable explanation of the problem.
        paths: Filesystem paths involved.
    """

    issue_type: TriageIssueType
    severity: TriageSeverity = TriageSeverity.WARNING
    action: TriageAction = TriageAction.REVIEW
    plex_key: str | None = None
    plex_title: str | None = None
    shoko_id: int | None = None
    shoko_name: str | None = None
    detail: str = ""
    paths: list[str] = Field(default_factory=list)


class TriageReport(BaseModel):
    """Combined triage report across Plex, Shoko, and filesystem data.

    Attributes:
        section_title: Name of the library section.
        total_shows: Total shows in the section.
        issues: All detected issues.
        summary: Human-readable summary with counts by type and severity.
    """

    section_title: str = ""
    total_shows: int = 0
    issues: list[TriageIssue] = Field(default_factory=list)
    summary: str = ""


class ShokoSeasonEntry(BaseModel):
    """A single Shoko series that maps to a season in TMDB.

    Attributes:
        shoko_id: Shoko series ID.
        name: Shoko series name.
        anidb_id: AniDB series ID.
        episode_count: Number of episodes in this Shoko series.
    """

    shoko_id: int
    name: str
    anidb_id: int = 0
    episode_count: int = 0


class PlexSeasonEntry(BaseModel):
    """A single season in Plex for a show.

    Attributes:
        season_number: Season number in Plex.
        title: Season title.
        episode_count: Number of episodes in this season.
    """

    season_number: int
    title: str = ""
    episode_count: int = 0


class SeasonGap(BaseModel):
    """Gap between expected and actual seasons for a show.

    Cross-references Shoko series (grouped by TMDB show ID) against
    Plex seasons to identify missing content.

    Attributes:
        plex_title: Title of the show in Plex (or best guess from Shoko).
        plex_key: Plex rating key (None if show not found in Plex).
        tmdb_show_id: TMDB show ID that groups the Shoko series.
        shoko_series: All Shoko series sharing this TMDB show ID.
        plex_seasons: Seasons currently in Plex (empty if show missing).
        expected_episode_count: Total episodes across all Shoko series.
        actual_episode_count: Total episodes currently in Plex.
        is_missing: Whether some expected content is not in Plex.
    """

    plex_title: str
    plex_key: str | None = None
    tmdb_show_id: int | None = None
    shoko_series: list[ShokoSeasonEntry] = Field(default_factory=list)
    plex_seasons: list[PlexSeasonEntry] = Field(default_factory=list)
    expected_episode_count: int = 0
    actual_episode_count: int = 0
    is_missing: bool = False


class SeasonGapReport(BaseModel):
    """Report of all season gaps between Shoko and Plex.

    Attributes:
        section_title: Name of the library section.
        total_shows: Total shows in the Plex section.
        gap_count: Number of shows with missing seasons.
        gaps: List of season gaps, sorted by episode deficit (largest first).
        summary: Human-readable summary.
    """

    section_title: str = ""
    total_shows: int = 0
    gap_count: int = 0
    gaps: list[SeasonGap] = Field(default_factory=list)
    summary: str = ""


# --- CSV-exportable flat models -----------------------------------------
#
# These models are designed for CSV tabular output. They flatten nested
# structures into a single row per item, making them suitable for spreadsheet
# analysis and re-ingest via `plexctl ingest`.
#


class CsvMediaMetadata(BaseModel):
    """Flat CSV row for MediaMetadata."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    rating: str = ""
    audience_rating: str = ""
    content_rating: str = ""
    studio: str = ""
    summary: str = ""


class CsvLibrarySection(BaseModel):
    """Flat CSV row for LibrarySection."""

    key: str
    title: str
    section_type: str = ""
    agent: str = ""
    scanner: str = ""
    language: str = ""
    count: str = ""


class CsvLibraryLocation(BaseModel):
    """Flat CSV row for LibraryLocation."""

    id: str
    path: str


class CsvMediaTreeItem(BaseModel):
    """Flat CSV row for MediaTreeItem."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    leaf_count: str = ""
    viewed_leaf_count: str = ""
    parent_key: str = ""
    parent_title: str = ""
    children: str = ""


class CsvCollectionMetadata(BaseModel):
    """Flat CSV row for CollectionMetadata."""

    key: str
    title: str
    smart: str = ""
    content_count: str = ""
    section_key: str = ""
    section_title: str = ""
    summary: str = ""
    thumb: str = ""
    art: str = ""
    added_at: str = ""
    updated_at: str = ""


class CsvCollectionInfo(BaseModel):
    """Flat CSV row for CollectionInfo."""

    key: str
    title: str
    smart: str = ""
    content_count: str = ""
    section_title: str = ""


class CsvShowDiagnostics(BaseModel):
    """Flat CSV row for ShowDiagnostics."""

    key: str
    title: str = ""
    year: str = ""
    locations: str = ""
    total_episodes: str = ""
    unanalyzed_episodes: str = ""
    multi_media_episodes: str = ""
    missing_file_episodes: str = ""


class CsvTriageIssue(BaseModel):
    """Flat CSV row for TriageIssue."""

    issue_type: str
    severity: str = ""
    action: str = ""
    plex_key: str = ""
    plex_title: str = ""
    shoko_id: str = ""
    shoko_name: str = ""
    detail: str = ""
    paths: str = ""


class CsvSeasonGap(BaseModel):
    """Flat CSV row for SeasonGap."""

    plex_title: str
    plex_key: str = ""
    tmdb_show_id: str = ""
    actual_episode_count: str = ""
    expected_episode_count: str = ""
    missing_episodes: str = ""
    is_missing: str = ""
    shoko_series: str = ""
    plex_seasons: str = ""


class CsvShokoSeries(BaseModel):
    """Flat CSV row for ShokoSeries."""

    id: str
    name: str
    anidb: str = ""
    episode_count: str = ""
    tmdb_shows: str = ""
    tmdb_movies: str = ""
    local_episodes: str = ""
    local_specials: str = ""


class CsvShokoFile(BaseModel):
    """Flat CSV row for ShokoFile."""

    id: str
    filename: str = ""
    relative_path: str = ""
    series_name: str = ""
    resolution: str = ""
    is_variation: str = ""
    is_ignored: str = ""
    is_accessible: str = ""
    crc32: str = ""
    ed2k: str = ""
    sha1: str = ""


class CsvShokoMismatch(BaseModel):
    """Flat CSV row for ShokoMismatch."""

    mismatch_type: str
    shoko_id: str = ""
    name: str = ""
    detail: str = ""
    severity: str = ""
    plex_key: str = ""


class CsvFsDir(BaseModel):
    """Flat CSV row for FsDir."""

    path: str
    name: str
    video_files: str = ""
    has_files: str = ""
    subdir_count: str = ""
    subdirs: str = ""
    is_plex_location: str = ""
    plex_shows: str = ""


class CsvShokoEpisode(BaseModel):
    """Flat CSV row for ShokoEpisode."""

    id: str = ""
    name: str = ""
    episode_number: str = ""
    episode_type: str = ""
    season_number: str = ""
    anidb_id: str = ""
    is_hidden: str = ""


class CsvMediaPartDetail(BaseModel):
    """Flat CSV row for MediaPartDetail."""

    file_path: str
    size: str = ""
    accessible: str = ""
    exists: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    container: str = ""
    resolution: str = ""
    bitrate: str = ""
    duration: str = ""


class CsvTmdbSearchResult(BaseModel):
    """Flat CSV row for TmdbSearchResult."""

    id: str = ""
    name: str = ""
    overview: str = ""
    year: str = ""
    first_aired: str = ""
    poster_url: str = ""


# --- Playback session models ---------------------------------------------


class PlaybackSession(BaseModel):
    """An active Plex playback session.

    Represents a single user currently playing media on the server.

    Attributes:
        session_key: Unique session identifier.
        user: Username of the person playing media.
        player_title: Name of the player device (e.g. "Chrome", "Roku").
        player_address: IP address of the player.
        state: Playback state — 'playing', 'paused', or 'buffering'.
        media_type: Type of media being played (e.g. 'movie', 'episode').
        title: Title of the media item.
        grandparent_title: Title of the parent show (for episodes).
        parent_title: Title of the season (for episodes).
        rating_key: Plex rating key of the media.
        duration: Total duration in milliseconds.
        view_offset: Current playback position in milliseconds.
        bitrate: Stream bitrate.
        video_codec: Video codec (e.g. 'h264', 'hevc').
        audio_codec: Audio codec (e.g. 'aac', 'ac3').
        container: Container format (e.g. 'mkv', 'mp4').
        transcoding: Whether the session is transcoding.
    """

    session_key: str
    user: str = ""
    player_title: str = ""
    player_address: str = ""
    state: str = ""
    media_type: str = ""
    title: str = ""
    grandparent_title: str | None = None
    parent_title: str | None = None
    rating_key: str = ""
    duration: int | None = None
    view_offset: int | None = None
    bitrate: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    container: str | None = None
    transcoding: bool = False


class UserAccount(BaseModel):
    """A Plex user account.

    Attributes:
        id: User account ID.
        username: User's username.
        email: User's email address.
        friend: Whether user is a friend on plex.tv.
        restricted: User access restrictions status.
        doh: DoH status.
        anonymous: Whether user is anonymous.
        title: Optional title/role.
        filtered: User list filtering status.
        customAvatar: Username or avatar URL.
        joinedAt: Account creation timestamp.
    """

    id: int
    username: str = ""
    email: str = ""
    friend: bool = False
    restricted: bool = False
    doh: bool = False
    anonymous: bool = False
    title: str = ""
    filtered: bool = False
    customAvatar: str = ""  # noqa: N815
    joinedAt: str | None = None  # noqa: N815


class CsvUserAccount(BaseModel):
    """Flat CSV row for UserAccount."""

    id: str = ""
    username: str = ""
    email: str = ""
    title: str = ""
    friend: str = ""
    restricted: str = ""


class ServerIdentity(BaseModel):
    """Plex server identity information.

    Attributes:
        machineIdentifier: Unique computer identifier.
        version: Plex Media Server version string.
        claimed: Whether the server has been claimed.
        size: Container size.
    """

    machineIdentifier: str = ""  # noqa: N815
    version: str = ""
    claimed: bool = False
    size: int = 0


class ServerPreference(BaseModel):
    """A single Plex server preference setting.

    Attributes:
        id: Preference key name.
        label: Human-readable label.
        value: Current value.
        type: Preference type (e.g. 'bool', 'text', 'int').
        default: Default value.
        summary: Description of the preference.
    """

    id: str
    label: str = ""
    value: str | bool | int | float = ""
    type: str = ""
    default: str | bool | int | float = ""
    summary: str = ""


class ServerInfo(BaseModel):
    """Plex Media Server identity and status information.

    Attributes:
        machine_id: Unique machine identifier.
        version: Server version string.
        platform: Server platform (e.g. 'Linux').
        platform_version: Platform version details.
        server_name: Display name of the server.
        owner: Plex account email of the server owner.
        product: Product name (e.g. 'Plex Media Server').
    """

    machine_id: str = ""
    version: str = ""
    platform: str = ""
    platform_version: str = ""
    server_name: str = ""
    owner: str = ""
    product: str = ""


class ButlerTask(BaseModel):
    """A Plex butler (background maintenance) task.

    Attributes:
        id: Task identifier.
        name: Human-readable task name.
        description: Description of what the task does.
        enabled: Whether the task is enabled.
        schedule: Schedule description (e.g. 'daily', 'weekly').
        last_run: Timestamp of the last run.
        next_run: Timestamp of the next scheduled run.
    """

    id: str = ""
    name: str = ""
    description: str = ""
    enabled: bool = True
    schedule: str = ""
    last_run: str | None = None
    next_run: str | None = None


# --- CRC audit models ------------------------------------------------------


class CrcAuditResult(BaseModel):
    """Result of a CRC hash audit for files in a Shoko series.

    Attributes:
        series_id: Shoko internal series ID.
        series_name: Name of the series.
        total_files: Total number of files in the series.
        files_with_crc: Files that have a real CRC32 hash in the filename.
        files_missing_crc: Files with %CRC placeholder (not yet hashed).
        files_no_bracket: Files without any CRC bracket notation.
        missing_crc_paths: Sample paths of files missing CRC hashes.
    """

    series_id: int
    series_name: str
    total_files: int = 0
    files_with_crc: int = 0
    files_missing_crc: int = 0
    files_no_bracket: int = 0
    missing_crc_paths: list[str] = Field(default_factory=list)


class CrcAuditReport(BaseModel):
    """Aggregated CRC audit report across all series.

    Attributes:
        total_series: Total number of series audited.
        total_files: Total number of files audited.
        files_with_crc: Files with real CRC32 hashes.
        files_missing_crc: Files with %CRC placeholder hashes.
        files_no_bracket: Files without any CRC bracket notation.
        series_missing_crc: Series that have files missing CRC hashes.
    """

    total_series: int = 0
    total_files: int = 0
    files_with_crc: int = 0
    files_missing_crc: int = 0
    files_no_bracket: int = 0
    series_missing_crc: list[CrcAuditResult] = Field(default_factory=list)


# --- TMDB Episode Group / Ordering models --------------------------------


class TmdbOrdering(BaseModel):
    """A TMDB episode group / alternate ordering for a show.

    TMDB shows (especially long-running anime) can have multiple
    episode orderings that group episodes into different season
    structures. For example, One Piece has "Sagas" (12 seasons),
    "TVDB Order" (23 seasons), "Seasons (Production)" (25 seasons), etc.

    The OrderingID uniquely identifies each ordering and is used
    to fetch its specific season/episode structure via the Shoko API.

    Attributes:
        ordering_id: Unique ID for this ordering (e.g. "62f98314175051007c594bdf").
            For the default ordering, this is the TMDB show ID as a string.
        name: Human-readable name (e.g. "TVDB Order", "Sagas").
        ordering_type: Type classification — integer (e.g. 1 for default seasons)
            or string (e.g. "OriginalAirDate").
        season_count: Number of seasons in this ordering.
        episode_count: Total episodes across all seasons.
        is_default: Whether this is TMDB's default season structure.
        is_preferred: Whether Shoko marks this as the preferred ordering.
        in_use: Whether this is the ordering currently active in Shoko.
    """

    ordering_id: str
    name: str
    ordering_type: int | str = 0
    season_count: int = 0
    episode_count: int = 0
    is_default: bool = False
    is_preferred: bool = False
    in_use: bool = False


# --- PlexMatch models ---------------------------------------------------


class PlexMatchEntry(BaseModel):
    """A single episode entry in a .plexmatch file.

    Maps an episode number to its actual file on disk. The filename
    should be a path relative to the .plexmatch file's directory
    (e.g. "Season 01/Episode.mkv" for files in subdirectories),
    or a bare filename for files in the same directory as .plexmatch.

    Attributes:
        season_number: Season number (e.g. 1 for S01).
        episode_number: Episode number within the season.
        filename: Path to the file relative to the .plexmatch directory.
    """

    season_number: int
    episode_number: int
    filename: str

    @classmethod
    def from_line(cls, line: str) -> PlexMatchEntry | None:
        """Parse an Episode line from a .plexmatch file.

        Expected format: ``Episode: S01E02: filename.mkv``

        Args:
            line: A single line from a .plexmatch file.

        Returns:
            PlexMatchEntry if the line parses successfully, None otherwise.
        """
        import re

        match = re.match(r"Episode:\s*S(\d+)E(\d+)\s*:\s*(.+)", line.strip(), re.IGNORECASE)
        if match is None:
            return None

        return cls(
            season_number=int(match.group(1)),
            episode_number=int(match.group(2)),
            filename=match.group(3).strip(),
        )


class PlexMatch(BaseModel):
    """A .plexmatch file for a series directory.

    Plexmatch files provide explicit metadata and file mappings for
    Plex to use when scanning a library, overriding filename-based
    matching. This is especially useful for anime libraries where
    filenames follow fansub conventions rather than Plex's expected
    naming patterns.

    Attributes:
        title: Series title (used as Title: line).
        year: Release/air year (used as Year: line).
        tvdb_id: TheTVDB ID (used as TvdbId: line).
        imdb_id: IMDb ID (used as ImdbId: line).
        tmdb_id: TMDB show ID (used as TmdbId: line, optional).
        entries: Episode mappings (used as Episode: lines).
    """

    title: str
    year: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None
    entries: list[PlexMatchEntry] = Field(default_factory=list)

    @classmethod
    def parse(cls, content: str) -> PlexMatch:
        """Parse a .plexmatch file string into a PlexMatch model.

        Reads the header lines (Title, Year, TvdbId, ImdbId, TmdbId) and
        Episode mappings from an existing .plexmatch file.

        Args:
            content: The .plexmatch file content to parse.

        Returns:
            PlexMatch with parsed metadata and episode entries.
        """
        title = ""
        year: int | None = None
        tvdb_id: int | None = None
        imdb_id: str | None = None
        tmdb_id: int | None = None
        entries: list[PlexMatchEntry] = []

        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("Title:"):
                title = line[len("Title:") :].strip()
            elif line.startswith("Year:"):
                year_str = line[len("Year:") :].strip()
                with contextlib.suppress(ValueError):
                    year = int(year_str)
            elif line.startswith("TvdbId:"):
                id_str = line[len("TvdbId:") :].strip()
                with contextlib.suppress(ValueError):
                    tvdb_id = int(id_str)
            elif line.startswith("ImdbId:"):
                imdb_id = line[len("ImdbId:") :].strip() or None
            elif line.startswith("TmdbId:"):
                id_str = line[len("TmdbId:") :].strip()
                with contextlib.suppress(ValueError):
                    tmdb_id = int(id_str)
            elif line.startswith("Episode:"):
                entry = PlexMatchEntry.from_line(line)
                if entry is not None:
                    entries.append(entry)

        return cls(
            title=title,
            year=year,
            tvdb_id=tvdb_id,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            entries=entries,
        )

    def merge(self, other: PlexMatch) -> PlexMatch:
        """Merge entries from another PlexMatch into this one.

        ``self`` entries take priority — when both sides have an entry for
        the same (season, episode) key, the entry from ``self`` is kept.
        Header metadata (title, year, IDs) from ``self`` is also preserved.

        This ordering lets callers write ``plexmatch.merge(existing)`` so
        that freshly-generated entries override stale file entries.

        Args:
            other: The PlexMatch whose entries provide fallback values.

        Returns:
            A new PlexMatch with merged entries, preserving self's header.
        """
        merged: dict[tuple[int, int], PlexMatchEntry] = {
            (e.season_number, e.episode_number): e for e in other.entries
        }
        for entry in self.entries:
            merged[(entry.season_number, entry.episode_number)] = entry

        merged_entries = sorted(
            merged.values(), key=lambda e: (e.season_number, e.episode_number)
        )

        return self.model_copy(update={"entries": merged_entries})

    def render(self) -> str:
        """Render the PlexMatch data as a .plexmatch file string.

        Returns:
            The complete .plexmatch file content.
        """
        lines: list[str] = [f"Title: {self.title}"]

        if self.year is not None:
            lines.append(f"Year: {self.year}")

        if self.tvdb_id is not None:
            lines.append(f"TvdbId: {self.tvdb_id}")

        if self.imdb_id is not None:
            lines.append(f"ImdbId: {self.imdb_id}")

        if self.tmdb_id is not None:
            lines.append(f"TmdbId: {self.tmdb_id}")

        lines.extend(
            f"Episode: S{entry.season_number:02d}E{entry.episode_number:02d}"
            f": {entry.filename}"
            for entry in self.entries
        )

        return "\n".join(lines)


class PlexMatchResult(BaseModel):
    """Result of generating a .plexmatch file for a single series or show.

    Tracks whether the plexmatch was successfully generated and written,
    or why it failed.

    Supports two naming conventions:
    - Shoko-based: series_id / series_name (legacy)
    - Plex-based: show_key / show_name (generic)

    Attributes:
        show_key: Plex rating key for the show (generic).
        show_name: Name of the show (generic).
        folder_name: Name of the matched directory on disk.
        folder_path: Full path to the series directory on disk.
        series_id: Shoko series ID (legacy, for Shoko compatibility).
        series_name: Name of the series in Shoko (legacy, for Shoko compatibility).
        success: Whether the .plexmatch was written successfully.
        error: Error message if generation failed.
        entry_count: Number of episode entries in the generated file.
    """

    show_key: str = ""
    show_name: str = ""
    folder_name: str = ""
    folder_path: str = ""
    series_id: int = 0
    series_name: str = ""
    success: bool = True
    error: str | None = None
    entry_count: int = 0


class PlexMatchBatchResult(BaseModel):
    """Aggregate result of batch .plexmatch generation.

    Attributes:
        total_dirs: Total directories scanned.
        matched: Directories matched to a Shoko series.
        generated: .plexmatch files successfully generated.
        failed: .plexmatch generations that failed.
        skipped: Directories with no matching Shoko series.
        results: Per-series results.
    """

    total_dirs: int = 0
    matched: int = 0
    generated: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[PlexMatchResult] = Field(default_factory=list)


class CsvCrcAuditResult(BaseModel):
    """Flat CSV row for CrcAuditResult."""

    series_id: str
    series_name: str = ""
    total_files: str = ""
    files_with_crc: str = ""
    files_missing_crc: str = ""
    files_no_bracket: str = ""
    missing_crc_paths: str = ""


class CsvPlaybackSession(BaseModel):
    """Flat CSV row for PlaybackSession."""

    session_key: str
    user: str = ""
    player_title: str = ""
    player_address: str = ""
    state: str = ""
    media_type: str = ""
    title: str = ""
    grandparent_title: str = ""
    parent_title: str = ""
    rating_key: str = ""
    duration: str = ""
    view_offset: str = ""
    bitrate: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    container: str = ""
    transcoding: str = ""


class CsvServerPreference(BaseModel):
    """Flat CSV row for ServerPreference."""

    id: str
    label: str = ""
    value: str = ""
    type: str = ""
    default: str = ""
    summary: str = ""


class CsvServerInfo(BaseModel):
    """Flat CSV row for ServerInfo."""

    machine_id: str = ""
    version: str = ""
    platform: str = ""
    platform_version: str = ""
    server_name: str = ""
    owner: str = ""
    product: str = ""


class CsvButlerTask(BaseModel):
    """Flat CSV row for ButlerTask."""

    id: str = ""
    name: str = ""
    description: str = ""
    enabled: str = ""
    schedule: str = ""
    last_run: str = ""
    next_run: str = ""


# --- Subtitle models --------------------------------------------------------


class SubtitleStreamInfo(BaseModel):
    """Information about a subtitle stream.

    Captures the key fields from plexapi's SubtitleStream object,
    normalized into a consistent shape for CLI output.

    Attributes:
        id: Unique stream ID on the server.
        language: Human-readable language name (e.g. 'English').
        language_code: ASCII language code (e.g. 'eng').
        language_tag: Two-letter language tag (e.g. 'en').
        title: Stream title.
        display_title: Display title shown in Plex UI.
        extended_display_title: Extended display title.
        codec: Codec name (e.g. 'srt', 'ass').
        format: Format name (e.g. 'srt').
        forced: Whether this is a forced subtitle.
        hearing_impaired: Whether this is an SDH subtitle.
        score: Match score for on-demand subtitles.
        provider: Provider title for on-demand subtitles.
        key: API URL path for this stream.
        selected: Whether this stream is currently selected.
        can_auto_sync: Whether auto-sync is available.
        perfect_match: Whether this is a perfect match.
        user_id: User ID that downloaded this on-demand subtitle.
    """

    id: int
    language: str = ""
    language_code: str = ""
    language_tag: str = ""
    title: str = ""
    display_title: str = ""
    extended_display_title: str = ""
    codec: str = ""
    format: str = ""
    forced: bool = False
    hearing_impaired: bool = False
    score: int | None = None
    provider: str = ""
    key: str = ""
    selected: bool = False
    can_auto_sync: bool = False
    perfect_match: bool = False
    user_id: int | None = None


class CsvSubtitleStreamInfo(BaseModel):
    """Flat CSV row for SubtitleStreamInfo."""

    id: str
    language: str = ""
    language_code: str = ""
    language_tag: str = ""
    title: str = ""
    display_title: str = ""
    extended_display_title: str = ""
    codec: str = ""
    format: str = ""
    forced: str = ""
    hearing_impaired: str = ""
    score: str = ""
    provider: str = ""
    key: str = ""
    selected: str = ""
    can_auto_sync: str = ""
    perfect_match: str = ""
    user_id: str = ""


# --- Search models --------------------------------------------------------


class SearchResult(BaseModel):
    """A single result from a Plex search.

    Captures the key fields returned by the Plex search and hub APIs,
    normalized into a consistent shape regardless of the search type.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title.
        media_type: Type of media (movie, show, episode, etc.).
        year: Release year.
        summary: Short description.
        rating: Audience rating (0-10).
        thumb: URL path to thumbnail/poster image.
        section_key: Library section key if available.
        section_title: Library section title if available.
    """

    key: str
    title: str = ""
    media_type: MediaType | None = None
    year: int | None = None
    summary: str | None = None
    rating: float | None = None
    thumb: str | None = None
    section_key: str | None = None
    section_title: str | None = None


class SimilarMedia(BaseModel):
    """A media item related to a reference item.

    Returned by the 'find similar' endpoint, these are items that
    Plex considers related to a given rating key.

    Attributes:
        key: Plex rating key.
        title: Display title.
        media_type: Type of media.
        year: Release year.
        similarity: Match confidence (0-100, higher is better).
        thumb: URL path to thumbnail/poster image.
    """

    key: str
    title: str = ""
    media_type: MediaType | None = None
    year: int | None = None
    similarity: int | None = None
    thumb: str | None = None


class UpdateInfo(BaseModel):
    """Information about an available Plex Media Server update.

    Attributes:
        version: Version string of the available update.
        added: New features in this version.
        fixed: Bug fixes in this version.
        download_url: URL to download the update.
        state: Update state (e.g. 'ready' or 'downloading').
        release_notes: Full release notes.
    """

    version: str = ""
    added: str = ""
    fixed: str = ""
    download_url: str = ""
    state: str = ""
    release_notes: str = ""


class BandwidthStats(BaseModel):
    """Bandwidth statistics entry.

    Attributes:
        at: Timestamp of the data point (ISO format string).
        bytes: Bytes transferred.
        lan: Whether this is local network traffic.
        timespan: Time granularity ("seconds", "hours", "days", "weeks", "months").
        account_id: Plex account ID filter, if specified.
        device_id: Device ID filter, if specified.
    """

    at: str = ""
    bytes: int = 0
    lan: bool = False
    timespan: str = "hours"
    account_id: int | None = None
    device_id: int | None = None


class ResourceStats(BaseModel):
    """Server resource utilization entry.

    Attributes:
        at: Timestamp of the data point (ISO format string).
        host_cpu: Host CPU utilization percentage.
        host_memory: Host memory utilization percentage.
        process_cpu: Plex process CPU utilization percentage.
        process_memory: Plex process memory utilization percentage.
        timespan: Time granularity.
    """

    at: str = ""
    host_cpu: float = 0.0
    host_memory: float = 0.0
    process_cpu: float = 0.0
    process_memory: float = 0.0
    timespan: int = 6


class CsvUpdateInfo(BaseModel):
    """Flat CSV row for UpdateInfo."""

    version: str = ""
    added: str = ""
    fixed: str = ""
    download_url: str = ""
    state: str = ""
    release_notes: str = ""


class CsvBandwidthStats(BaseModel):
    """Flat CSV row for BandwidthStats."""

    at: str = ""
    bytes: str = ""
    lan: str = ""
    timespan: str = ""
    account_id: str = ""
    device_id: str = ""


class CsvResourceStats(BaseModel):
    """Flat CSV row for ResourceStats."""

    at: str = ""
    host_cpu: str = ""
    host_memory: str = ""
    process_cpu: str = ""
    process_memory: str = ""
    timespan: str = ""


class CsvSearchResult(BaseModel):
    """Flat CSV row for SearchResult."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    summary: str = ""
    rating: str = ""
    thumb: str = ""
    section_key: str = ""
    section_title: str = ""


class CsvSimilarMedia(BaseModel):
    """Flat CSV row for SimilarMedia."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    similarity: str = ""
    thumb: str = ""


# --- Smart Playlist models -------------------------------------------------


# Plex media type codes for the type= query parameter
PLAYLIST_TYPE_MAP: dict[str, str] = {"video": "1", "audio": "2", "photo": "3"}


class PlaylistType(StrEnum):
    """Plex playlist content types for smart playlist creation.

    These map to the 'type' parameter in the Plex playlist query API.
    """

    VIDEO = "video"
    AUDIO = "audio"
    PHOTO = "photo"


class SmartPlaylistFilter(BaseModel):
    """A single filter condition for a smart playlist.

    Represents a field=value pair used to build the smart playlist query.
    Plex uses operators like =, !=, >=, <=, >, <, contains, etc.

    Attributes:
        field: The Plex filter field name (e.g. 'year', 'genre', 'title').
        operator: Comparison operator (e.g. '=', '>=', '!=', 'contains').
            Defaults to '=' for exact match.
        value: The filter value to match against.
    """

    field: str
    operator: str = "="
    value: str


class SmartPlaylist(BaseModel):
    """Metadata about a Plex smart playlist.

    Attributes:
        key: Playlist rating key (unique identifier).
        title: Display title of the playlist.
        playlist_type: Content type (video, audio, photo).
        smart: Whether this is a smart (dynamic) playlist.
        item_count: Number of items matching the smart filter.
        composite: URL path to the playlist thumbnail/poster.
        added_at: When the playlist was created.
        updated_at: When the playlist was last updated.
        filters: Parsed filter conditions (populated from content query).
    """

    key: str
    title: str
    playlist_type: PlaylistType | None = None
    smart: bool = True
    item_count: int = 0
    composite: str | None = None
    added_at: int | str | None = None
    updated_at: int | str | None = None
    filters: list[SmartPlaylistFilter] = Field(default_factory=list)


class Playlist(BaseModel):
    """Metadata about a Plex regular (manual) playlist.

    Regular playlists contain a fixed set of items managed by
    adding/removing individual items, unlike smart playlists
    which use dynamic filter queries.

    Attributes:
        key: Playlist rating key (unique identifier).
        title: Display title of the playlist.
        playlist_type: Content type (video, audio, photo).
        smart: Always False for regular playlists.
        item_count: Number of items in the playlist.
        composite: URL path to the playlist thumbnail/poster.
        added_at: When the playlist was created.
        updated_at: When the playlist was last updated.
    """

    key: str
    title: str
    playlist_type: PlaylistType | None = None
    smart: bool = False
    item_count: int = 0
    composite: str | None = None
    added_at: int | str | None = None
    updated_at: int | str | None = None


class PlaylistItem(BaseModel):
    """A single item within a playlist.

    Represents a media item returned by a playlist query.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title.
        media_type: Type of media (movie, show, episode, etc.).
        year: Release year.
        duration: Duration in milliseconds.
        thumb: URL path to thumbnail/poster image.
    """

    key: str
    title: str = ""
    media_type: MediaType | None = None
    year: int | None = None
    duration: int | None = None
    thumb: str | None = None


class M3UEntry(BaseModel):
    """A single parsed entry from an M3U file.

    Attributes:
        raw: The original line from the file (without extension).
        track_number: Optional track number prefix (e.g. ``01``).
        artists: Comma-separated artist names parsed from the filename.
        title: Track title parsed from the filename.
    """

    raw: str
    track_number: int | None = None
    artists: str = ""
    title: str = ""


class PlaylistImportResult(BaseModel):
    """Result of importing an M3U file into a Plex playlist.

    Attributes:
        playlist_key: Rating key of the created playlist (empty on failure).
        playlist_title: Title of the created playlist.
        total: Total entries parsed from the M3U file.
        matched: Entries that matched a Plex track.
        unmatched: Entries that found no matching Plex track.
        unmatched_entries: The raw lines that could not be matched.
    """

    playlist_key: str = ""
    playlist_title: str = ""
    total: int = 0
    matched: int = 0
    unmatched: int = 0
    unmatched_entries: list[str] = Field(default_factory=list)


class CsvSmartPlaylistFilter(BaseModel):
    """Flat CSV row for SmartPlaylistFilter."""

    field: str
    operator: str = ""
    value: str


class CsvSmartPlaylist(BaseModel):
    """Flat CSV row for SmartPlaylist."""

    key: str
    title: str
    playlist_type: str = ""
    smart: str = ""
    item_count: str = ""
    composite: str = ""
    added_at: str = ""
    updated_at: str = ""
    filters: str


class CsvPlaylist(BaseModel):
    """Flat CSV row for Playlist."""

    key: str
    title: str
    playlist_type: str = ""
    smart: str = ""
    item_count: str = ""
    composite: str = ""
    added_at: str = ""
    updated_at: str = ""


class CsvPlaylistItem(BaseModel):
    """Flat CSV row for PlaylistItem."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    duration: str = ""
    thumb: str = ""


# --- Photo models ----------------------------------------------------------


class PhotoAlbumInfo(BaseModel):
    """Metadata about a Plex photo album.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title of the album.
        sort_title: Title used for sorting.
        summary: Album description.
        thumb: URL path to thumbnail/poster image.
        photo_count: Number of photos in the album.
        user_rating: User-assigned rating.
    """

    key: str
    title: str
    sort_title: str | None = None
    summary: str | None = None
    thumb: str | None = None
    photo_count: int = 0
    user_rating: float | None = None


class PhotoInfo(BaseModel):
    """Metadata about a single Plex photo.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title of the photo.
        sort_title: Title used for sorting.
        album: Name of the parent album.
        album_key: Rating key of the parent album.
        originally_available: Original capture/date string.
        thumb: URL path to thumbnail image.
        user_rating: User-assigned rating.
        media_type: Always 'photo'.
        year: Year the photo was taken.
        tags: Pipe-separated tag labels.
    """

    key: str
    title: str
    sort_title: str | None = None
    album: str | None = None
    album_key: str | None = None
    originally_available: str | None = None
    thumb: str | None = None
    user_rating: float | None = None
    media_type: str = "photo"
    year: int | None = None
    tags: str | None = None


class CsvPhotoAlbumInfo(BaseModel):
    """Flat CSV row for PhotoAlbumInfo."""

    key: str
    title: str = ""
    sort_title: str = ""
    summary: str = ""
    thumb: str = ""
    photo_count: str = ""
    user_rating: str = ""


class CsvPhotoInfo(BaseModel):
    """Flat CSV row for PhotoInfo."""

    key: str
    title: str = ""
    sort_title: str = ""
    album: str = ""
    album_key: str = ""
    originally_available: str = ""
    thumb: str = ""
    user_rating: str = ""
    media_type: str = ""
    year: str = ""
    tags: str = ""


# --- Watch history models -------------------------------------------------


class WatchHistoryEntry(BaseModel):
    """A single entry from the Plex watch history.

    Attributes:
        key: Plex rating key of the viewed item.
        title: Display title of the item.
        media_type: Type of media (movie, episode, track, etc.).
        year: Release year.
        viewed_at: When the item was viewed (ISO format string).
        account_id: Plex account ID of the viewer.
        device_id: Device ID used for playback.
        parent_title: Album name for tracks, Season name for episodes.
        grandparent_title: Artist for tracks, Show name for episodes.
    """

    key: str
    title: str
    media_type: str = ""
    year: int | None = None
    viewed_at: str | None = None
    account_id: int | None = None
    device_id: int | None = None
    parent_title: str | None = None
    grandparent_title: str | None = None


class CsvWatchHistoryEntry(BaseModel):
    """Flat CSV row for WatchHistoryEntry."""

    key: str
    title: str = ""
    media_type: str = ""
    year: str = ""
    viewed_at: str = ""
    account_id: str = ""
    device_id: str = ""
    parent_title: str = ""
    grandparent_title: str = ""


# --- Transcode session models ----------------------------------------------


class TranscodeSessionInfo(BaseModel):
    """Information about an active Plex transcode session.

    Attributes:
        key: Transcode session key.
        throttled: Whether transcoding is throttled.
        progress: Transcoding progress percentage.
        speed: Transcoding speed relative to real-time.
        error: Whether the session has an error.
        duration: Duration of the transcoded content in milliseconds.
        context: Transcode context (e.g. 'streaming', 'conversions').
        source_video: Source video codec.
        source_audio: Source audio codec.
        target_video: Target video codec.
        target_audio: Target audio codec.
        video_decision: Video transcode decision (e.g. 'transcode', 'direct play').
        audio_decision: Audio transcode decision.
        protocol: Streaming protocol.
    """

    key: str
    throttled: bool = False
    progress: float = 0.0
    speed: float = 0.0
    error: bool = False
    duration: int = 0
    context: str = ""
    source_video: str = ""
    source_audio: str = ""
    target_video: str = ""
    target_audio: str = ""
    video_decision: str = ""
    audio_decision: str = ""
    protocol: str = ""


class CsvTranscodeSessionInfo(BaseModel):
    """Flat CSV row for TranscodeSessionInfo."""

    key: str
    throttled: str = ""
    progress: str = ""
    speed: str = ""
    error: str = ""
    duration: str = ""
    context: str = ""
    source_video: str = ""
    source_audio: str = ""
    target_video: str = ""
    target_audio: str = ""
    video_decision: str = ""
    audio_decision: str = ""
    protocol: str = ""


# --- Music models -----------------------------------------------------------


class ArtistInfo(BaseModel):
    """Metadata about a Plex music artist.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Display title / artist name.
        sort_title: Title used for sorting.
        summary: Artist biography / description.
        thumb: URL path to thumbnail/poster image.
        art: URL path to background art image.
        genre: Primary genre tag.
        country: Country of origin.
        album_count: Number of albums by this artist.
        rating: Critic rating (0-10).
        user_rating: User rating (0-10).
    """

    key: str
    title: str
    sort_title: str | None = None
    summary: str | None = None
    thumb: str | None = None
    art: str | None = None
    genre: str | None = None
    country: str | None = None
    album_count: int = 0
    rating: float | None = None
    user_rating: float | None = None


class AlbumInfo(BaseModel):
    """Metadata about a Plex music album.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Album title.
        sort_title: Title used for sorting.
        artist: Parent artist name.
        artist_key: Parent artist rating key.
        year: Release year.
        summary: Album description.
        thumb: URL path to thumbnail/poster image.
        genre: Primary genre tag.
        studio: Record label / studio.
        track_count: Number of tracks on this album.
        rating: Critic rating (0-10).
        user_rating: User rating (0-10).
        originally_available: Original release date.
    """

    key: str
    title: str
    sort_title: str | None = None
    artist: str | None = None
    artist_key: str | None = None
    year: int | None = None
    summary: str | None = None
    thumb: str | None = None
    genre: str | None = None
    studio: str | None = None
    track_count: int = 0
    rating: float | None = None
    user_rating: float | None = None
    originally_available: str | None = None


class TrackInfo(BaseModel):
    """Metadata about a Plex music track.

    Attributes:
        key: Plex rating key (unique identifier).
        title: Track title.
        sort_title: Title used for sorting.
        artist: Grandparent artist name.
        artist_key: Grandparent artist rating key.
        album: Parent album title.
        album_key: Parent album rating key.
        track_number: Track number within the album.
        disc_number: Disc number for multi-disc albums.
        duration: Duration in milliseconds.
        year: Release year.
        genre: Primary genre tag.
        rating: Critic rating (0-10).
        user_rating: User rating (0-10).
        view_count: Number of times this track has been played.
        media_type: Always "track".
    """

    key: str
    title: str
    sort_title: str | None = None
    artist: str | None = None
    artist_key: str | None = None
    album: str | None = None
    album_key: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    duration: int | None = None
    year: int | None = None
    genre: str | None = None
    rating: float | None = None
    user_rating: float | None = None
    view_count: int = 0
    media_type: str = "track"


class CsvArtistInfo(BaseModel):
    """Flat CSV row for ArtistInfo."""

    key: str
    title: str = ""
    sort_title: str = ""
    summary: str = ""
    thumb: str = ""
    art: str = ""
    genre: str = ""
    country: str = ""
    album_count: str = ""
    rating: str = ""
    user_rating: str = ""


class CsvAlbumInfo(BaseModel):
    """Flat CSV row for AlbumInfo."""

    key: str
    title: str = ""
    sort_title: str = ""
    artist: str = ""
    artist_key: str = ""
    year: str = ""
    summary: str = ""
    thumb: str = ""
    genre: str = ""
    studio: str = ""
    track_count: str = ""
    rating: str = ""
    user_rating: str = ""
    originally_available: str = ""


class CsvTrackInfo(BaseModel):
    """Flat CSV row for TrackInfo."""

    key: str
    title: str = ""
    sort_title: str = ""
    artist: str = ""
    artist_key: str = ""
    album: str = ""
    album_key: str = ""
    track_number: str = ""
    disc_number: str = ""
    duration: str = ""
    year: str = ""
    genre: str = ""
    rating: str = ""
    user_rating: str = ""
    view_count: str = ""
    media_type: str = ""
