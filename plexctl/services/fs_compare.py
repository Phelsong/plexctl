"""Filesystem comparison service for Plex media libraries.

Compares the actual filesystem structure with Plex's view of the library
to identify orphaned directories, multi-location shows, and grouping issues
that affect ShokoRelay scanner behavior.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from plexctl.models import VIDEO_EXTENSIONS, FsCompareResult, FsDir, ReorgAction, ReorganizePlan

if TYPE_CHECKING:
    from plexctl.client import PlexClient


class FsCompareService:
    """Service for comparing filesystem structure with Plex's library view.

    Walks the section's root directories on disk and cross-references
    with Plex's show locations to identify:
    - Orphaned directories (on disk but not tracked by Plex)
    - Multi-location shows (Plex show backed by multiple filesystem dirs)
    - Grouped directories (files + subdirs, which can cause ShokoRelay issues)

    Args:
        client: Connected PlexClient instance.
        path_map: Optional mapping from Plex/server paths to local filesystem
            paths. For example, if Plex sees ``/data/anime`` but the local
            machine mounts it at ``/mnt/nfs/media/anime``, pass
            ``{"/data": ""}``.
    """

    def __init__(self, client: PlexClient, path_map: dict[str, str] | None = None) -> None:
        self._client = client
        self._path_map = path_map or {}

    def _to_local_path(self, server_path: str) -> str:
        f"""Convert a Plex/server path to a local filesystem path.

        Uses the path_map to translate Docker container paths or remote
        paths to local mount points.

        Args:
            server_path: Path as reported by Plex (e.g. '/data/anime/Show').

        Returns:
            Local filesystem path (e.g. '/<plexroot>/anime/Show').
        """
        for server_prefix, local_prefix in self._path_map.items():
            if server_path.startswith(server_prefix):
                return server_path.replace(server_prefix, local_prefix, 1)
        return server_path

    def _to_server_path(self, local_path: str) -> str:
        """Convert a local filesystem path to a Plex/server path.

        Args:
            local_path: Local filesystem path (e.g. '/<plexroot>/anime/Show').

        Returns:
            Server path as Plex would report it (e.g. '/data/anime/Show').
        """
        for server_prefix, local_prefix in self._path_map.items():
            if local_path.startswith(local_prefix):
                return local_path.replace(local_prefix, server_prefix, 1)
        return local_path

    @staticmethod
    def _count_video_files(directory: Path) -> int:
        """Count video files directly in a directory (non-recursive).

        Args:
            directory: Path to scan for video files.

        Returns:
            Number of files with video extensions.
        """
        if not directory.is_dir():
            return 0

        count = 0
        with suppress(PermissionError):
            for entry in directory.iterdir():
                if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS:
                    count += 1
        return count

    @staticmethod
    def _has_files(directory: Path) -> bool:
        """Check if a directory contains any regular files (non-recursive).

        Stops at the first regular file found — much faster than counting
        all video files, making it suitable for slow network mounts.

        Args:
            directory: Path to check for files.

        Returns:
            True if the directory contains at least one regular file.
        """
        if not directory.is_dir():
            return False
        with suppress(PermissionError):
            return any(entry.is_file() for entry in directory.iterdir())
        return False

    @staticmethod
    def _get_subdirs(directory: Path) -> list[str]:
        """Get names of immediate subdirectories.

        Args:
            directory: Path to scan for subdirectories.

        Returns:
            Sorted list of subdirectory names.
        """
        if not directory.is_dir():
            return []

        subdirs: list[str] = []
        with suppress(PermissionError):
            subdirs.extend(
                entry.name
                for entry in directory.iterdir()
                if entry.is_dir() and not entry.name.startswith(".")
            )
        return sorted(subdirs)

    def compare_section(
        self, section_title: str, max_depth: int = 2, count_files: bool = False
    ) -> FsCompareResult:
        """Compare a section's filesystem with Plex's show locations.

        Walks the section root directories on disk and cross-references
        each directory against Plex's known show locations. Identifies
        orphaned dirs, multi-location shows, and grouping risks.

        Uses ``path_map`` (from constructor) to translate between
        Plex server paths and local filesystem paths.

        Args:
            section_title: Library section name (e.g. 'Anime').
            max_depth: Maximum directory depth to walk (default 2: root/season).
            count_files: If True, count video files in each directory (slow on NFS).

        Returns:
            FsCompareResult with comparison details.

        Raises:
            ValueError: If section is not a show library.
        """
        section = self._client.server.library.section(section_title)
        if section.type != "show":
            msg = f"Section '{section_title}' is type '{section.type}', expected 'show'"
            raise ValueError(msg)

        # Build a map: local_path -> [show_title, ...]
        # Plex reports server paths; we convert to local paths for filesystem walking.
        section_locations = list(getattr(section, "locations", []))
        shows = section.all()

        # Map server paths to local paths for filesystem walking
        local_roots = [self._to_local_path(p) for p in section_locations]

        path_to_shows: dict[str, list[str]] = {}
        multi_location: list[tuple[str, list[str]]] = []

        for show in shows:
            locations = list(getattr(show, "locations", []))
            # Convert server paths to local paths for filesystem matching
            local_locations = [self._to_local_path(p) for p in locations]
            if len(locations) > 1:
                show_title = getattr(show, "title", str(show.ratingKey))
                multi_location.append((show_title, local_locations))
            for loc in local_locations:
                path_to_shows.setdefault(loc, []).append(
                    getattr(show, "title", str(show.ratingKey))
                )

        # Walk each section root directory using local paths
        all_dirs: list[FsDir] = []
        orphan_dirs: list[FsDir] = []
        grouped_dirs: list[FsDir] = []

        for local_root in local_roots:
            root = Path(local_root)
            if not root.is_dir():
                continue
            self._walk_directory(
                root=root,
                path_to_shows=path_to_shows,
                all_dirs=all_dirs,
                orphan_dirs=orphan_dirs,
                grouped_dirs=grouped_dirs,
                max_depth=max_depth,
                current_depth=0,
                count_files=count_files,
            )

        plex_tracked = sum(1 for d in all_dirs if d.is_plex_location)

        return FsCompareResult(
            section_root=", ".join(local_roots),
            section_title=section_title,
            scanner=getattr(section, "scanner", None),
            total_dirs=len(all_dirs),
            plex_tracked_dirs=plex_tracked,
            orphan_dirs=orphan_dirs,
            multi_location_shows=multi_location,
            grouped_dirs=grouped_dirs,
        )

    def _walk_directory(
        self,
        root: Path,
        path_to_shows: dict[str, list[str]],
        all_dirs: list[FsDir],
        orphan_dirs: list[FsDir],
        grouped_dirs: list[FsDir],
        max_depth: int = 2,
        current_depth: int = 0,
        count_files: bool = False,
    ) -> None:
        """Walk a section root directory and classify each subdirectory.

        Args:
            root: Path object for the directory to walk.
            path_to_shows: Map of local filesystem paths to Plex show titles.
            all_dirs: Accumulator for all directories found.
            orphan_dirs: Accumulator for directories not tracked by Plex.
            grouped_dirs: Accumulator for directories with grouping risk.
            max_depth: Maximum depth to recurse (0 = root only, 1 = one level deep).
            current_depth: Current recursion depth.
            count_files: If True, count video files (slow on network mounts).
        """
        if current_depth > max_depth:
            return
        try:
            entries = sorted(root.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            # Fast file presence check stops at first regular file.
            # Full video count is only computed when count_files=True.
            has_files = self._has_files(entry)
            video_count = self._count_video_files(entry) if count_files else 0
            subdirs = self._get_subdirs(entry)
            subdir_count = len(subdirs)

            plex_shows = path_to_shows.get(str(entry), [])
            is_plex_location = len(plex_shows) > 0

            fs_dir = FsDir(
                path=str(entry),
                name=entry.name,
                video_files=video_count,
                has_files=has_files,
                subdir_count=subdir_count,
                subdirs=subdirs,
                is_plex_location=is_plex_location,
                plex_shows=plex_shows,
            )

            all_dirs.append(fs_dir)

            if not is_plex_location:
                orphan_dirs.append(fs_dir)

            # Grouped dirs: have both files AND subdirectories.
            # This is the ShokoRelay grouping risk scenario — files at
            # the same level as season subdirs can cause unexpected merges.
            # Use has_files when count_files=False (video_count is 0 then).
            has_video = video_count > 0 if count_files else has_files
            if has_video and subdir_count > 0:
                grouped_dirs.append(fs_dir)

            # Recurse into subdirectories (depth-limited)
            self._walk_directory(
                root=entry,
                path_to_shows=path_to_shows,
                all_dirs=all_dirs,
                orphan_dirs=orphan_dirs,
                grouped_dirs=grouped_dirs,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                count_files=count_files,
            )

    def list_orphans(
        self, section_title: str, max_depth: int = 2, count_files: bool = False
    ) -> list[FsDir]:
        """Find directories on disk that Plex doesn't track as show locations.

        These are directories under the section root path that don't appear
        in any Plex show's ``locations`` list. Orphaned dirs may indicate:
        - Files Shoko couldn't match (no AniDB entry)
        - Directories Plex split or merged differently
        - New files not yet scanned

        Args:
            section_title: Library section name (e.g. 'Anime').
            max_depth: Maximum directory depth to walk.

        Returns:
            List of FsDir objects for orphaned directories.
        """
        result = self.compare_section(section_title, max_depth=max_depth, count_files=count_files)
        return result.orphan_dirs

    def list_grouped(
        self, section_title: str, max_depth: int = 2, count_files: bool = False
    ) -> list[FsDir]:
        """Find directories that have both files and subdirectories.

        These are the ShokoRelay grouping risk: when a directory has files
        directly in it AND subdirectories, the scanner removes it from
        Plex's normal grouping and scans subdirs independently. This can
        cause unexpected behavior.

        Args:
            section_title: Library section name (e.g. 'Anime').
            max_depth: Maximum directory depth to walk.

        Returns:
            List of FsDir objects for grouped directories.
        """
        result = self.compare_section(section_title, max_depth=max_depth, count_files=count_files)
        return result.grouped_dirs

    def reorganize_plan(self, section_title: str, max_depth: int = 2) -> ReorganizePlan:
        """Generate a reorganization plan to fix Plex parsing issues.

        Analyzes the filesystem structure and Plex's show locations to
        propose concrete actions that would resolve grouping risks,
        multi-location merges, and orphan directories.

        All actions are proposals — nothing is executed automatically.

        Args:
            section_title: Library section name (e.g. 'Anime').
            max_depth: Maximum directory depth to walk.

        Returns:
            ReorganizePlan with proposed actions and summary.
        """
        result = self.compare_section(section_title, max_depth=max_depth, count_files=False)
        actions: list[ReorgAction] = []

        # Action 1: Grouped directories — propose splitting subdirs to top-level.
        # When a dir has both files and subdirs, ShokoRelay handles it by
        # scanning each subdir independently. But this can cause issues when
        # the subdirs are different seasons of the same show that should be
        # grouped together. Moving subdirs to top-level eliminates the grouping
        # risk and gives each series its own clean directory.
        for fs_dir in result.grouped_dirs:
            for subdir_name in fs_dir.subdirs:
                src = f"{fs_dir.path}/{subdir_name}"
                # Destination: move to section root as a top-level dir.
                # This is safe because ShokoRelay scans top-level dirs as series.
                dest = f"{result.section_root}/{subdir_name}"
                actions.append(
                    ReorgAction(
                        action="move",
                        source=src,
                        destination=dest,
                        reason=(
                            f"'{fs_dir.name}' has files + subdirs (grouping risk). "
                            f"Moving '{subdir_name}' to top-level eliminates "
                            f"ShokoRelay split behavior."
                        ),
                        risk="medium",
                    )
                )

        # Action 2: Multi-location shows — flag for review.
        # These are shows where Shoko intentionally merged multiple AniDB
        # entries. The user needs to decide whether this is desired or not.
        # We can't automatically fix this — it requires Shoko config changes.
        for show_title, locations in result.multi_location_shows:
            actions.append(
                ReorgAction(
                    action="review",
                    source=locations[0],
                    destination=locations[1] if len(locations) > 1 else None,
                    reason=(
                        f"'{show_title}' maps {len(locations)} filesystem dirs "
                        f"to one Plex show. This may cause duplicate episodes. "
                        f"Review in Shoko to decide if these should be separate series."
                    ),
                    risk="high",
                )
            )

        # Action 3: Orphans — categorize by risk.
        orphans_with_files = [d for d in result.orphan_dirs if d.has_files or d.video_files > 0]
        empty_orphans = [d for d in result.orphan_dirs if d.video_files == 0 and not d.has_files]

        # Orphans with files and subdirs are likely unrecognized season dirs.
        for fs_dir in orphans_with_files:
            if fs_dir.subdir_count > 0:
                actions.append(
                    ReorgAction(
                        action="review",
                        source=fs_dir.path,
                        reason=(
                            f"'{fs_dir.name}' has files+subdirs but Plex doesn't "
                            f"track it. May be an unrecognized series. Consider "
                            f"adding to Shoko or restructuring."
                        ),
                        risk="medium",
                    )
                )
            else:
                # Flat orphan with files — likely an unmatched series.
                actions.append(
                    ReorgAction(
                        action="review",
                        source=fs_dir.path,
                        reason=(
                            f"'{fs_dir.name}' has files but Plex doesn't track it. "
                            f"Check if Shoko can match these files, or fix filenames."
                        ),
                        risk="low",
                    )
                )

        # Empty orphans — safe to remove or keep as-is.
        actions.extend(
            ReorgAction(
                action="remove_empty",
                source=fs_dir.path,
                reason=(f"'{fs_dir.name}' is empty and not tracked by Plex. Safe to remove."),
                risk="low",
            )
            for fs_dir in empty_orphans[:10]
        )
        if len(empty_orphans) > 10:
            actions.append(
                ReorgAction(
                    action="remove_empty",
                    source=f"{len(empty_orphans) - 10} more empty directories",
                    reason=(
                        f"An additional {len(empty_orphans) - 10} empty "
                        f"directories exist that Plex doesn't track."
                    ),
                    risk="low",
                )
            )

        # Build summary
        grouped_count = len(result.grouped_dirs)
        multi_count = len(result.multi_location_shows)
        orphan_file_count = len(orphans_with_files)
        empty_count = len(empty_orphans)

        lines = [
            f"Found {grouped_count} grouping-risk dirs " f"(files + subdirs at same level).",
            f"Found {multi_count} multi-location shows (multiple dirs → 1 Plex show).",
            f"Found {orphan_file_count} orphan dirs with files, " f"{empty_count} empty orphans.",
        ]
        if grouped_count > 0:
            lines.append(
                "Recommended: Move season subdirs to top-level to eliminate "
                "ShokoRelay grouping behavior."
            )
        if multi_count > 0:
            lines.append(
                "Multi-location shows require Shoko config review — "
                "cannot be fixed from Plex alone."
            )

        return ReorganizePlan(
            section_title=section_title,
            total_actions=len(actions),
            actions=actions,
            summary="\n".join(lines),
        )
