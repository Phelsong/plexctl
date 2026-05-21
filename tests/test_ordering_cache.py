"""Test ordering preference cache."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from plexctl.ordering_cache import (
    get_ordering_preference,
    load_ordering_preferences,
    remove_ordering_preference,
    save_ordering_preference,
)


def _make_cache_dir(tmp_path: Path) -> Path:
    """Create a mock config dir and return the expected cache path."""
    cache_path = tmp_path / "ordering_preferences.toml"
    return cache_path


def test_save_and_load_preference(tmp_path: Path) -> None:
    """Save a preference and load it back."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        result = save_ordering_preference(65942, "641eb9d6b234b9007ac67063")
        assert result == cache_path
        assert cache_path.exists()

        prefs = load_ordering_preferences()
        assert prefs[65942] == "641eb9d6b234b9007ac67063"


def test_get_ordering_preference(tmp_path: Path) -> None:
    """get_ordering_preference returns stored value or None."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        assert get_ordering_preference(65942) is None

        save_ordering_preference(65942, "abc123")
        assert get_ordering_preference(65942) == "abc123"
        assert get_ordering_preference(99999) is None


def test_remove_ordering_preference(tmp_path: Path) -> None:
    """Remove a stored preference."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        save_ordering_preference(65942, "abc123")
        assert get_ordering_preference(65942) == "abc123"

        removed = remove_ordering_preference(65942)
        assert removed is True
        assert get_ordering_preference(65942) is None

        # Removing again returns False
        removed = remove_ordering_preference(65942)
        assert removed is False


def test_overwrite_preference(tmp_path: Path) -> None:
    """Saving a preference for the same show overwrites the old one."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        save_ordering_preference(65942, "old-ordering")
        save_ordering_preference(65942, "new-ordering")

        assert get_ordering_preference(65942) == "new-ordering"


def test_multiple_preferences(tmp_path: Path) -> None:
    """Multiple shows can have different ordering preferences."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        save_ordering_preference(65942, "ordering-a")
        save_ordering_preference(37854, "ordering-b")

        prefs = load_ordering_preferences()
        assert prefs[65942] == "ordering-a"
        assert prefs[37854] == "ordering-b"


def test_load_missing_file(tmp_path: Path) -> None:
    """Loading preferences from a nonexistent file returns empty dict."""
    cache_path = tmp_path / "nonexistent" / "ordering_preferences.toml"
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        prefs = load_ordering_preferences()
        assert prefs == {}


def test_load_invalid_toml(tmp_path: Path) -> None:
    """Loading preferences from invalid TOML returns empty dict."""
    cache_path = _make_cache_dir(tmp_path)
    cache_path.write_text("this is not valid TOML {{{", encoding="utf-8")
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        prefs = load_ordering_preferences()
        assert prefs == {}


def test_remove_last_preference_empties_file(tmp_path: Path) -> None:
    """Removing the last preference writes an empty file."""
    cache_path = _make_cache_dir(tmp_path)
    with patch("plexctl.ordering_cache._cache_path", return_value=cache_path):
        save_ordering_preference(65942, "abc123")
        remove_ordering_preference(65942)

        # File should still exist but be empty
        content = cache_path.read_text(encoding="utf-8")
        assert content.strip() == ""