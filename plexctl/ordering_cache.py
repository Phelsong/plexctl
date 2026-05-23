"""Ordering preference cache for TMDB episode group orderings.

Stores a mapping of TMDB show ID → preferred ordering ID in a TOML file
at the plexctl config directory. This lets users declare which TMDB
episode ordering to use for multi-season anime (e.g. Re:Zero) instead
of relying on Shoko's unreliable is_preferred/is_default flags.

File format (ordering_preferences.toml):

    [preferences]
    65942 = "641eb9d6b234b9007ac67063"
    37854 = "62f98314175051007c594bdf"
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)


def _cache_path() -> Path:
    """Return the path to the ordering preferences cache file."""
    from plexctl.config import config_dir

    return Path(config_dir()) / "ordering_preferences.toml"


def load_ordering_preferences() -> dict[int, str]:
    """Load ordering preferences from the cache file.

    Returns:
        Dict mapping TMDB show ID to ordering ID string.
        Returns empty dict if the file doesn't exist or is invalid.
    """
    path = _cache_path()
    if not path.is_file():
        return {}

    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Could not read ordering preferences from %s: %s", path, exc)
        return {}

    preferences = data.get("preferences", {})
    if not isinstance(preferences, dict):
        return {}

    # Convert string keys to int (TOML requires string keys in tables)
    result: dict[int, str] = {}
    for key, value in preferences.items():
        try:
            tmdb_id = int(key)
            result[tmdb_id] = str(value)
        except (ValueError, TypeError):
            logger.debug("Skipping invalid preference key: %s", key)

    return result


def save_ordering_preference(tmdb_show_id: int, ordering_id: str) -> Path:
    """Save or update a single ordering preference.

    Reads the existing preferences, updates the entry for the given
    TMDB show ID, and writes the file back.

    Args:
        tmdb_show_id: TMDB TV show ID.
        ordering_id: The preferred ordering ID string.

    Returns:
        The path to the written cache file.
    """
    path = _cache_path()
    current = load_ordering_preferences()
    current[tmdb_show_id] = ordering_id

    # Build TOML content manually (simple format, no external writer needed)
    lines = ["[preferences]"]
    lines.extend(f'{show_id} = "{current[show_id]}"' for show_id in sorted(current))
    content = "\n".join(lines) + "\n"

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    logger.info("Saved ordering preference: TMDB show %d → %s", tmdb_show_id, ordering_id)
    return path


def remove_ordering_preference(tmdb_show_id: int) -> bool:
    """Remove an ordering preference for a TMDB show.

    Args:
        tmdb_show_id: TMDB TV show ID to remove.

    Returns:
        True if a preference was removed, False if it didn't exist.
    """
    current = load_ordering_preferences()
    if tmdb_show_id not in current:
        return False

    del current[tmdb_show_id]
    path = _cache_path()

    if current:
        lines = ["[preferences]"]
        lines.extend(f'{show_id} = "{current[show_id]}"' for show_id in sorted(current))
        content = "\n".join(lines) + "\n"
    else:
        content = ""

    path.write_text(content, encoding="utf-8")
    return True


def get_ordering_preference(tmdb_show_id: int) -> str | None:
    """Look up a stored ordering preference for a TMDB show.

    Args:
        tmdb_show_id: TMDB TV show ID.

    Returns:
        The preferred ordering ID string, or None if no preference is stored.
    """
    preferences = load_ordering_preferences()
    return preferences.get(tmdb_show_id)
