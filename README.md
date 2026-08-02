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
# List library sections
plexctl library list

# List movies (default: Movies section, 25 results)
plexctl movies
plexctl movies --section "Anime Movies" --limit 50

# List TV shows
plexctl shows --section Anime --limit 10

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

# Ingest items (import from CSV)
plexctl item ingest list
plexctl item ingest --file items.csv
plexctl item ingest triage_issue items.csv

# Actor, director, genre lookup
plexctl item actor 32272
plexctl item director 32272
plexctl item genre 32272

# Additional search options
plexctl get 32272                     # Get by id
plexctl matches 32272                 # Show matches
plexctl fix-match 32272               # Fix a match
plexctl unmatch 32272                 # Unmatch
plexctl similar 32272                 # Similar items
plexctl tmdb 32272                    # Show TMDB details
```

### Library Commands

```bash
# Library management
plexctl library list
plexctl library get --id 1
plexctl library create --name "Anime"
plexctl library delete --name "Anime"
plexctl library update --name "Movies" --name "New Name"
plexctl library locations --name "Movies"

# Collections (sub-group)
plexctl library collections list --section Anime
plexctl library collections get --section Anime --collection-name "Best Anime"
plexctl library collections create --section Anime --title "Best Anime" --items 32272,61464
plexctl library collections update --section Anime --collection-name "Best Anime" --title "Updated Title"
plexctl library collections delete --section Anime --collection-name "Best Anime"
plexctl library collections add --section Anime --collection-name "Best Anime" --item 61464
plexctl library collections remove --section Anime --collection-name "Best Anime" --item 61464

# Playlists (sub-group)
plexctl library playlists list --section Anime
plexctl library playlists get --section Anime --playlist-name "Favorites"
plexctl library playlists create --section Anime --title "Favorites"
plexctl library playlists update --section Anime --playlist-name "Favorites" --title "Updated"
plexctl library playlists delete --section Anime --playlist-name "Favorites"
plexctl library playlists items --section Anime --playlist-name "Favorites"
plexctl library playlists add --section Anime --playlist-name "Favorites" --item 32272
plexctl library playlists remove --section Anime --playlist-name "Favorites" --item 32272
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
plexctl movies --section "anime" --limit 50       # List 50 anime movies
plexctl movies --tree                           # Show tree view
plexctl movies --tree --section "Anime Movies"   # Tree view of anime
```

### Shows Navigation

```bash
# Browse shows
plexctl shows                                    # List shows
plexctl shows --section "Anime" --limit 10       # List anime shows

# Navigate with tree
plexctl shows tree --section Anime               # Show tree of series
plexctl shows tree --section Anime --tree-id 42  # Navigate into series

# Show details and seasons
plexctl shows show --section Anime --show-id 42  # Show series details
plexctl shows season --section Anime --show-id 42 --season-id 1  # Show season details
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

# Season gap analysis
plexctl triage seasons --section Anime
plexctl triage seasons --section Anime --missing-only

# Triage fixes
plexctl triage fix --section Anime --action analyze
plexctl triage seasons --section Anime

# Diagnostics
plexctl triage diagnose scan --section Anime
plexctl triage diagnose-show --show-id 61464
plexctl triage diagnose-files --show-id 61464
plexctl triage analyze --show-id 61464

# Batch operations
plexctl triage batch-analyze --section Anime
plexctl triage batch-refresh --section Anime
plexctl triage refresh --show-id 61464 --section Anime
plexctl triage scan --section Anime
plexctl triage split --show-id 61464
plexctl triage remove-duplicates --section Anime
plexctl triage remove-duplicates --section Anime --no-dry-run

# Matches
plexctl triage matches --show-id 61464
plexctl triage fix-match --show-id 61464 --search-result-id 12345
plexctl triage unmatch --show-id 61464

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
plexctl playlists smart update --name "Anime Classics"
plexctl playlists smart delete --name "Anime Classics"
plexctl playlists smart items --name "Anime Classics"
plexctl playlists smart add --name "Anime Classics" --item 32272
plexctl playlists smart remove --name "Anime Classics" --item 32272
```

### Shoko Server Commands (Core Plugin)

```bash
# List series
plexctl shoko series --limit 10
plexctl shoko series --search "One Piece"

# List episodes for a series
plexctl shoko episodes 1

# List or search files
plexctl shoko files --limit 20
plexctl shoko files --search "One_Piece"

# Find unlinked files (not associated with any series)
plexctl shoko unlinked --limit 10

# Find series with problems
plexctl shoko problems --limit 20

# TMDB linking
plexctl shoko search-tmdb "One Piece"
plexctl shoko link-tmdb 1 12345                # link TMDB show
plexctl shoko link-tmdb 1 12345 --movie        # link TMDB movie
plexctl shoko unlink-tmdb 1 12345
plexctl shoko refresh-tmdb 1

# CRC hash audit
plexctl shoko crc-audit                        # audit all files for CRC completeness
plexctl shoko batch-rehash                     # rehash ALL files missing CRC32 hashes

# PlexMatch TMDB orderings
plexctl shoko plexmatch-orderings 75            # list TMDB episode orderings for a series

# File actions
plexctl shoko rehash 12345                     # trigger CRC rehash for one file
plexctl shoko rescan 12345                     # trigger AniDB rescan
plexctl shoko trigger-import                   # import new files from disk
plexctl shoko update-media-info                # update all media info
```

### PlexMatch Generation

Generate `.plexmatch` files that tell Plex exactly how to match files to episodes, overriding filename-based matching. This is especially useful for anime libraries where filenames follow fansub naming conventions.

```bash
# Generate .plexmatch for a single series (prints to stdout)
plexctl shoko plexmatch 42

# Write to a specific file
plexctl shoko plexmatch 42 -o .plexmatch

# Write directly into the series directory
plexctl shoko plexmatch 42 --write-to-dir "/<plexroot>/anime/One Piece"

# Generate .plexmatch for ALL series in a library directory
plexctl shoko plexmatch-all

# Specify a different library or media root
plexctl shoko plexmatch-all --library tv
plexctl shoko plexmatch-all --media-root /mnt/nfs/media

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

# Apply an ordering to all series in a library
plexctl shoko plexmatch-all --ordering 62f98314175051007c594bdf
```

When `--ordering` is specified, plexctl fetches the alternate season structure from TMDB via the Shoko API and remaps episode season/episode numbers accordingly. The ordering is applied by matching TMDB episode IDs — episodes not found in the alternate ordering fall back to their default season/episode assignment.

## Deprecated Commands

**Note:** The following commands still work for backward compatibility but will show deprecation warnings. For new projects, use the updated command structure:

| Old Command                          | New Command                     |
|-------------------------------------|---------------------------------|
| `plexctl diagnose`                  | `plexctl triage`                |
| `plexctl fix`                       | `plexctl triage`                |
| `plexctl fsck`                      | `plexctl triage`                |
| `plexctl search`                    | `plexctl item search`           |
| `plexctl collections` [standalone]  | `plexctl library collections`   |
| `plexctl tree`                      | `plexctl shows tree`            |

**Migration path example:**
```bash
# Old (deprecated)
plexctl diagnose scan --section Anime
plexctl fix matches 61464
plexctl fsck scan --section Anime

# New (recommended)
plexctl triage diagnose scan --section Anime
plexctl triage matches --show-id 61464
plexctl triage fsck-scan --section Anime
```

### CSV Output

Any command that displays tabular data can export to CSV:

```bash
# Export to stdout as CSV
plexctl library list --csv

# Export to a file
plexctl library list --csv --output sections.csv

# All major commands support --csv and --output
plexctl movies --section Anime --csv --output anime_movies.csv
plexctl shoko series --csv --output shoko_series.csv
plexctl triage report --section Anime --csv --output triage_report.csv
plexctl item search "One Piece" --csv --output search_results.csv
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

Available models: `media_metadata`, `library_section`, `collection_info`, `show_diagnostics`, `triage_issue`, `season_gap`, `shoko_series`, `shoko_file`, `shoko_mismatch`, `shoko_episode`, `episode_diagnostics`, `media_part_detail`, `tmdb_search_result`, `fs_dir`, `crc_audit_result`

## Architecture

### Commands
user facing interface

### Services
logic layer

### Models

- **30+ Pydantic models** for all data types (media_metadata, triage_issue, show_diagnostics, shoko_series, shoko_file, tmdb_search_result, etc.)
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

# Lint
pixi run lint

# Format
pixi run format

# Type check
pixi run typecheck

# Run tests
pixi run test

# Run all checks
pixi run lint && pixi run format --check && pixi run typecheck && pixi run test
```

## License

MIT