from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

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
