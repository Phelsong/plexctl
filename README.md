# plexctl

A CLI toolkit for managing Plex Media Server. 
NOTE: Github is a push-only mirror

## Features

- **Item commands** — Browse, search, and edit Plex library metadata with focused commands
- **Library management** — Organize collections and playlists within Plex libraries
- **Movies section** — Browse movies with flexible filtering options
- **Shows navigation** — Explore TV shows with tree and season navigation
- **Manage Playlists** — Add, edit, import playlists (+smart)
- **Server commands** — Monitor sessions, manage preferences, and automate backups
- **Season gap analysis** — Find missing seasons by comparing with Plex shows
- **Triage** — Diagnose and fix issuses
- **Filesystem comparison** — Compare disk structure with Plex's library view
- **Fix operations** — Batch analyze, split multi-location shows, remove duplicates, fix matches
- **PlexMatch generation** — Generate `.plexmatch` files for accurate Plex scanning
- **CSV I/O** — Export any command output as CSV, ingest CSV back into validated models
- **Plugins** — Extensible plugin support for cross referencing against connected services (Shoko is the reference implementation)
- **Shoko integration** — Query Shoko Server for anime metadata, TMDB linking, CRC audits (Core Plugin)

## Requirements
- Python 3.12+
- [pixi](https://pixi.sh) (recommended) or pip
- A Plex Media Server with accessible API
- (Optional) Shoko Server for anime-specific features

## Installation

### Development
#### With pixi (recommended)

```bash
pixi install
pixi run plexctl
```
### Packaged (linux only atm)

```bash
pixi run install
```

## Configuration

Create a config file at `~/.config/plexctl/plexctl.toml`:

```toml
[plex]
url = "https://plex.example.com"
token = "your-plex-token-here"
media_root = "/mnt/nfs/media"

[shoko]
url = "https://shoko.example.com"
apikey = "your-shoko-apikey-here"
media_root = "/mnt/nfs/media/anime"
```

**Priority order:** environment variables > `.env` file (for dev) > `plexctl.toml` > defaults

🔒 **File permissions:** plexctl warns if the config file is readable by group/other. Fix with:
```bash
chmod 400 ~/.config/plexctl/plexctl.toml
```

### Configuration reference

| TOML key          | Env var            | Required | Description                                        |
|-------------------|--------------------|----------|----------------------------------------------------|
| `plex.url`        | `PLEX_URL`         | Yes      | Plex server URL                                    |
| `plex.token`      | `PLEX_TOKEN`       | Yes      | Plex API token                                     |
| `plex.media_root` | `PLEX_MEDIA_ROOT`  | No       | Default media root (default: `/mnt/nfs/media`)     |
| `shoko.url`       | `SHOKO_URL`        | No*      | Shoko Server URL                                   |
| `shoko.apikey`    | `SHOKO_KEY`        | No*      | Shoko API key                                      |
| `shoko.media_root`| `SHOKO_MEDIA_ROOT` | No       | Shoko media root (default: `/mnt/nfs/media/anime`) |

\* Required for `shoko`, `triage`, and `crc` commands

### Getting your Plex token

(future onboard commands will walk thru this process)
1. Open Plex in a browser
2. Browse to any media item → ... → Info → View XML
3. The `X-Plex-Token` query parameter in the URL is your token

### Getting your Shoko API key

1. Open Shoko Server web UI
2. Go to Settings → API Keys (or use `POST /api/auth` with your credentials)

## Usage Examples

### Item Commands

```bash
# Search by title (item search)
plexctl item search "One Piece" --section Anime

# Show detailed metadata for a specific item
plexctl item info 32272

# Edit metadata
plexctl item edit 32272 title "New Title"
plexctl item edit 32272 summary "Updated description"

# Rate and watch status
plexctl item rate 32272
plexctl item watch 32272
plexctl item unwatch 32272

```

### Library Commands

```bash
# Library management
plexctl library list
plexctl library create --name "Anime"
plexctl library locations --name "Movies"

# Collections (sub-group)
plexctl library collections list --section Anime
plexctl library collections create --section Anime --title "Best Anime" --items 32272,61464
plexctl library collections add --section Anime --collection-name "Best Anime" --item 61464

```

### Server Commands

```bash
# Active server commands
plexctl server sessions
plexctl server info
plexctl server prefs
plexctl server set-pref --key "Clean Bundles" --value 1
plexctl server butler
plexctl server butler-run --action "Back up section"
```

### Movies Section

```bash
# Browse movies
plexctl movies                                    # List 25 movies
plexctl movies --tree --section "Anime Movies"   # Tree view of anime
```

### Shows Navigation

```bash
# Browse shows
plexctl shows                                    # List shows
plexctl shows --section "Anime" --limit 10       # List anime shows

# Navigate with tree
plexctl shows tree --section Anime               # Show tree of series
```

### Triage Commands

```bash

# Path mapping
# If Plex runs in Docker with a different filesystem path than your local machine, use `--path-map` to translate paths:
# Plex sees /data/anime, local machine has /mnt/nfs/media/anime
plexctl triage fsck-scan --section Anime --path-map /data=/mnt/nfs/media

# Triage reports
plexctl triage report --section Anime --path-map /data=/mnt/nfs/media
plexctl triage report --section Anime --filter-severity error
plexctl triage report --section Anime --filter-action analyze

# Triage fixes
plexctl triage fix --section Anime --action analyze
plexctl triage seasons --section Anime
plexctl triage matches --show-id 61464
plexctl triage fix-match --show-id 61464 --search-result-id 12345

# Diagnostics
plexctl triage diagnose scan --section Anime
plexctl triage diagnose-show --show-id 61464
plexctl triage diagnose-files --show-id 61464
plexctl triage analyze --show-id 61464

# Batch operations
plexctl triage batch-analyze --section Anime
plexctl triage batch-refresh --section Anime
plexctl triage split --show-id 61464
plexctl triage remove-duplicates --section Anime

# Matches

# Filesystem comparison (fsck)
plexctl triage fsck-scan --section Anime --path-map /data=/mnt/nfs/media
plexctl triage fsck-orphans --section Anime --path-map /data=/mnt/nfs/media
plexctl triage fsck-grouped --section Anime --path-map /data=/mnt/nfs/media
plexctl triage fsck-reorganize --section Anime --path-map /data=/mnt/nfs/media

# Triage management
plexctl triage merge --source-show-id 41 --target-show-id 42
plexctl triage empty-trash --section Anime
plexctl triage ingest list
plexctl triage ingest triage_issue triage_report.csv
```

### (Smart)Playlists Commands

```bash
# SmartPlaylists operations
plexctl playlists create --name "Anime Classics"
plexctl playlists get --name "Anime Classics"
plexctl playlists smart list
plexctl playlists smart add --name "Anime Classics" --item 32272
```

### Shoko Server Commands (Core Plugin)

```bash
# List series
plexctl shoko series 

# List episodes for a series
plexctl shoko episodes 1

# List or search files
plexctl shoko files --search "One_Piece"

# Find unlinked files (not associated with any series)
plexctl shoko unlinked --limit 10

# Find series with problems
plexctl shoko problems --limit 20

# CRC hash audit
plexctl shoko crc-audit                        # audit all files for CRC completeness
plexctl shoko batch-rehash                     # rehash ALL files missing CRC32 hashes
```

### PlexMatch Generation

Generate `.plexmatch` files that tell Plex exactly how to match files to episodes, overriding filename-based matching. This is especially useful for anime libraries where filenames follow fansub naming conventions.

```bash
# Generate .plexmatch for a single series (prints to stdout)
plexctl shoko plexmatch 42

# Write to a specific file
plexctl shoko plexmatch 42 -o .plexmatch

# Generate .plexmatch for ALL series in a library directory
plexctl shoko plexmatch-all --library tv

# Preview what would be done without writing files
plexctl shoko plexmatch-all --dry-run
```

The generated `.plexmatch` file looks like:

```
Title: Witch Watch
Year: 2025
TvdbId: 453127
TmdbId: 261868
Episode: S01E01: Witch_Watch_-_01_(1920x1080_HEVC_10bit)_[F15DB9CE].mkv
Episode: S01E02: Witch_Watch_-_02_(1920x1080_HEVC_10bit)_[788CDEAC].mkv
...
```

When `--write-to-dir` is used, filenames become paths relative to the `.plexmatch` location:

```
Episode: S01E01: Season 01/Witch_Watch_-_01_(1920x1080_HEVC_10bit)_[F15DB9CE].mkv
```

**Key behaviors:**
- Uses TMDB cross-reference data for season/episode numbering (falls back to AniDB numbering)
- Specials are mapped to season 0 (S00E01, S00E02, etc.)
- Episodes without TMDB season/episode mapping (e.g. OVAs) default to season 0
- When multiple Shoko series share one TMDB show (e.g. multi-cour anime), they are combined into a single `.plexmatch`
- Deduplicates entries when multiple files map to the same season/episode
- Excludes hidden episodes, variation files, and ignored files

#### TMDB Episode Orderings

Long-running anime often have multiple season structures on TMDB. For example, One Piece has a default "Seasons" ordering (23 seasons), a "TVDB Order" (24 seasons), "Sagas" (12 seasons), and more. By default, plexctl uses the ordering Shoko has active, but you can select any alternate ordering with `--ordering`.

```bash
# List available TMDB episode orderings for a series
plexctl shoko plexmatch-orderings 75

# Output:
#   Ordering ID              Name               Seasons  Episodes  Flags
#   37854                    Seasons                 23      1202  default
#   62f98314175051007c594bdf  TVDB Order             24      1200
#   5ae1bc83c3a36876a700ce68  Sagas                  12      1202  preferred, in-use
#   ...more orderings...

# Use a specific ordering when generating .plexmatch
plexctl shoko plexmatch 75 --ordering 62f98314175051007c594bdf
```

When `--ordering` is specified, plexctl fetches the alternate season structure from TMDB via the Shoko API and remaps episode season/episode numbers accordingly. The ordering is applied by matching TMDB episode IDs — episodes not found in the alternate ordering fall back to their default season/episode assignment.

### CSV Output

Any command that displays tabular data can export to CSV:

```bash
# Export to stdout as CSV
plexctl library list --csv

# Export to a file
plexctl library list --csv --output sections.csv

# All major commands support --csv and --output
plexctl triage report --section Anime --csv --output triage_report.csv
```

### Ingest

Read CSV files back into validated Pydantic models:

```bash
# List available model names
plexctl item ingest list

# Ingest a CSV file
plexctl item ingest triage_issue triage_report.csv
plexctl item ingest shoko_series shoko_series.csv
```

## Architecture

### Commands
user facing interface

### Services
logic layer

### Models

- **Pydantic models** for all data types (media_metadata, triage_issue, show_diagnostics, shoko_series, shoko_file, tmdb_search_result, etc.)
- **Rich model → CSV model** converters for all export formats
- **Config models** (PlexConfig, ShokoConfig) with validation

### Data Flow

```
CLI command → Command module → Service → Client → Plex API / Shoko API
                      ↓
                   Models (Pydantic validation)
                      ↓
               Rich tables or CSV output
```

All services accept a client instance and return validated Pydantic models. Commands handle CLI presentation (Rich tables) and CSV export.

## Development

```bash
# Install with dev dependencies
pixi install
pixi run -e dev pytest

# Format
pixi run format

# Run tests
pixi run test

# Run all checks
pixi run pre-commit
```

<!-- BEGIN COMMAND TREE -->

## `item`

Operations on individual media items.

- **`item search`** — Search for media by title.
- **`item edit`** — Edit a metadata field for a media item.
- **`item ingest`** — Read CSV data back into validated Pydantic models.
- **`item info`** — Show detailed metadata for a media item.
- **`item rate`** — Set the user rating for a media item.
- **`item watch`** — Mark a media item as watched.
- **`item unwatch`** — Mark a media item as unwatched.
- **`item delete`** — Delete a media item from the library.
- **`item matches`** — Search for metadata matches for an item.
- **`item fix-match`** — Fix an incorrect metadata match.
- **`item unmatch`** — Remove metadata match from an item.
- **`item get`** — Find a media item by its Plex rating key.
- **`item advanced`** — Advanced search with multiple filters.
- **`item actor`** — Search for media featuring a specific actor.
- **`item director`** — Search for media directed by a specific director.
- **`item genre`** — Search for media by genre.
- **`item title`** — Search for media by title.
- **`item year`** — Search for media by release year.
- **`item similar`** — Find media similar to a given item.
- **`item tmdb`** — Search for media using TMDB-integrated search.
- **`item add-genre`** — Add genre
- **`item remove-genre`** — Remove genre
- **`item add-collection`** — Add collection
- **`item remove-collection`** — Remove collection
- **`item add-label`** — Add label
- **`item remove-label`** — Remove label
- **`item add-director`** — Add director
- **`item remove-director`** — Remove director
- **`item add-writer`** — Add writer
- **`item remove-writer`** — Remove writer
- **`item add-mood`** — Add mood
- **`item remove-mood`** — Remove mood
- **`item add-style`** — Add style
- **`item remove-style`** — Remove style
- **`item add-country`** — Add country
- **`item remove-country`** — Remove country
- **`item lock`** — Lock metadata field(s) to prevent automatic changes.
- **`item unlock`** — Unlock metadata field(s) to allow automatic changes.
- **`item search-subs`** — Search for available subtitles for a media item.
- **`item download-sub`** — Download (apply) a subtitle to a media item.
- **`item upload-sub`** — Upload a subtitle file for a media item.
- **`item remove-sub`** — Remove a subtitle from a media item.
- **`item set-progress`** — Set playback progress for a media item.
- **`item merge`** — Merge multiple media items into one.

## `library`

Manage Plex library sections and collections.

- **`library list`** — List all library sections on the server.
- **`library get`** — Get details for a specific library section.
- **`library create`** — Create a new library section.
- **`library delete`** — Delete a library section permanently.
- **`library update`** — Update a library section's settings.
- **`library collections`** — Manage Plex collections.
  - **`library collections list`** — List all collections, optionally filtered by section.
  - **`library collections get`** — Get detailed metadata for a collection.
  - **`library collections create`** — Create a new collection in a library section.
  - **`library collections update`** — Update a collection's metadata.
  - **`library collections delete`** — Delete a collection permanently.
  - **`library collections add`** — Add items to a collection.
  - **`library collections remove`** — Remove items from a collection.
- **`library playlists`** — Manage Plex playlists (regular and smart).
  - **`library playlists list`** — List all regular (non-smart) playlists.
  - **`library playlists get`** — Get detailed metadata for a regular playlist.
  - **`library playlists create`** — Create a new regular playlist.
  - **`library playlists update`** — Update a playlist's title.
  - **`library playlists delete`** — Delete a playlist permanently.
  - **`library playlists items`** — List items contained in a playlist.
  - **`library playlists add`** — Add items to a playlist.
  - **`library playlists remove`** — Remove items from a playlist.
  - **`library playlists import`** — Import an M3U file into a new Plex audio playlist.
  - **`library playlists generate-m3u`** — Generate an M3U playlist from audio files in a directory.
  - **`library playlists smart`** — Manage smart playlists with dynamic filters.
    - **`library playlists smart create`** — Create a new smart playlist with dynamic query filters.
    - **`library playlists smart get`** — Get detailed metadata for a smart playlist.
    - **`library playlists smart list`** — List all smart playlists, optionally filtered by section.
    - **`library playlists smart update`** — Update a smart playlist's title, filters, or sort order.
    - **`library playlists smart delete`** — Delete a smart playlist permanently.
    - **`library playlists smart items`** — List items contained in a smart playlist.

## `movies`

Browse movies in your library.

- **`movies`** — Browse movies in your library.

## `music`

Browse and manage music libraries.

- **`music`** *(default)* — Browse and manage music libraries.
- **`music albums`** — List albums, optionally filtered by artist.
- **`music tracks`** — List tracks, optionally filtered by album or artist.
- **`music tree`** — Browse a music library section as a hierarchical tree.
- **`music recently-added`** — Show recently added music.

## `photos`

Browse and manage photo libraries.

- **`photos`** *(default)* — Browse photo albums in your library.
- **`photos list`** — List photos, optionally filtered by album.
- **`photos tree`** — Browse a photo library section as a hierarchical tree.
- **`photos recently-added`** — List recently added photo albums.

## `shows`

Browse TV shows in your library.

- **`shows`** *(default)* — Browse TV shows in your library.
- **`shows tree`** — Browse a library section as a hierarchical tree.
- **`shows show`** — Show seasons and episodes for a show as a tree.
- **`shows season`** — Show episodes in a season as a tree.

## `playlists`

Manage Plex playlists (regular and smart).

- **`playlists list`** — List all regular (non-smart) playlists.
- **`playlists get`** — Get detailed metadata for a regular playlist.
- **`playlists create`** — Create a new regular playlist.
- **`playlists update`** — Update a playlist's title.
- **`playlists delete`** — Delete a playlist permanently.
- **`playlists items`** — List items contained in a playlist.
- **`playlists add`** — Add items to a playlist.
- **`playlists remove`** — Remove items from a playlist.
- **`playlists import`** — Import an M3U file into a new Plex audio playlist.
- **`playlists generate-m3u`** — Generate an M3U playlist from audio files in a directory.
- **`playlists smart`** — Manage smart playlists with dynamic filters.
  - **`playlists smart create`** — Create a new smart playlist with dynamic query filters.
  - **`playlists smart get`** — Get detailed metadata for a smart playlist.
  - **`playlists smart list`** — List all smart playlists, optionally filtered by section.
  - **`playlists smart update`** — Update a smart playlist's title, filters, or sort order.
  - **`playlists smart delete`** — Delete a smart playlist permanently.
  - **`playlists smart items`** — List items contained in a smart playlist.

## `triage`

Unified diagnostics, fixes, and filesystem checks for Plex.

- **`triage report`** — Generate a unified triage report combining all data sources.
- **`triage fix`** — Execute auto-fixable triage actions.
- **`triage diagnose`** — Scan a library section for shows with file parsing issues.
- **`triage diagnose-show`** — Diagnose a single show by rating key.
- **`triage diagnose-files`** — Show detailed file information for a specific episode.
- **`triage analyze`** — Trigger Plex to re-analyze a media item or section.
- **`triage batch-analyze`** — Re-analyze all shows with problems in a section.
- **`triage batch-refresh`** — Refresh metadata for all shows with problems in a section.
- **`triage refresh`** — Refresh metadata for an item or entire section.
- **`triage scan`** — Scan a library section for new or changed files.
- **`triage split`** — Split a multi-location show into separate entries.
- **`triage remove-duplicates`** — Remove duplicate media versions from episodes.
- **`triage matches`** — Search for metadata matches for an item.
- **`triage fix-match`** — Fix an incorrect metadata match.
- **`triage unmatch`** — Remove metadata match from an item.
- **`triage fsck-scan`** — Compare a section's filesystem with Plex's show locations.
- **`triage fsck-orphans`** — List directories on disk that Plex doesn't track.
- **`triage fsck-grouped`** — List directories with both files+subdirectories (grouping risk).
- **`triage fsck-reorganize`** — Generate a reorganization plan to fix Plex parsing issues.
- **`triage plexmatch`** — Generate a .plexmatch file for a Plex show using metadata only.
- **`triage plexmatch-all`** — Generate .plexmatch files for all shows in a section.
- **`triage ingest`** — Read CSV data back into validated Pydantic models.
- **`triage merge`** — Merge multiple media items into one.
- **`triage empty-trash`** — Empty the trash for a library section.

## `server`

Plex server administration and playback commands.

- **`server sessions`** — List active playback sessions on the server.
- **`server merge`** — Merge multiple media items into one.
- **`server empty-trash`** — Empty the trash for a library section.
- **`server info`** — Display Plex server identity and version information.
- **`server prefs`** — List Plex server preference settings.
- **`server set-pref`** — Set a server preference value.
- **`server butler`** — List all butler (background maintenance) tasks.
- **`server butler-run`** — Run a butler task immediately.
- **`server history`** — Display watch history for the server.
- **`server stop-session`** — Stop an active playback session.
- **`server on-deck`** — Show On Deck items.
- **`server recently-added`** — Show recently added items.
- **`server continue-watching`** — Show Continue Watching items.
- **`server get-transcodes`** — List active transcode sessions.
- **`server check-update`** — Check for available Plex Media Server updates.
- **`server install-update`** — Install the latest available Plex Media Server update.
- **`server bandwidth`** — Show server bandwidth statistics.
- **`server resources`** — Show server resource utilization (CPU/memory).
- **`server download-logs`** — Download Plex Media Server logs.
- **`server download-dbs`** — Download Plex Media Server databases for backup.
- **`server accounts`** — List Plex account users.

## `types`

get plex types

- **`types types`** — print reference types to the console

## `shoko`

Query Shoko Server for anime metadata and file information.

- **`shoko search-tmdb`** — Search TMDB for shows/movies to link to Shoko series.
- **`shoko link-tmdb`** — Link a TMDB show/movie to a Shoko series.
- **`shoko unlink-tmdb`** — Remove a TMDB show link from a Shoko series.
- **`shoko refresh-tmdb`** — Refresh TMDB show metadata for a Shoko series.
- **`shoko crc-audit`** — Audit all Shoko files for CRC hash completeness.
- **`shoko rehash`** — Trigger a CRC rehash for a single file in Shoko.
- **`shoko rescan`** — Trigger an AniDB rescan for a single file in Shoko.
- **`shoko trigger-import`** — Trigger Shoko to import new files from disk.
- **`shoko batch-rehash`** — Trigger CRC rehash for all files missing CRC32 hashes.
- **`shoko season-gaps`** — Cross-reference Shoko series with Plex to find missing seasons.
- **`shoko update-media-info`** — Trigger Shoko to update all media info (codec analysis etc).
- **`shoko plexmatch`** — Generate a .plexmatch file for a series using Shoko data.
- **`shoko orderings`** — List available TMDB episode orderings for a series.
- **`shoko plexmatch-prefer`** — Set or remove a preferred TMDB ordering for a series.
- **`shoko plexmatch-all`** — Generate .plexmatch files for all series in a library directory.

---
*Total active commands: 137*


<!-- END COMMAND TREE -->

## License

MIT
