# plexctl Command Reference

Auto-generated command tree for plexctl.
This document lists all active (non-deprecated) commands.

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
- **`server install-update`** — Install the latest available Plex Media Server update (`--tonight`, `--skip`).
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

## `plexctl`

- **`repl`** — Start an interactive REPL for running plexctl commands.
- **`help`** — Show help for plexctl or a specific command.

---
*Total active commands: 139*
