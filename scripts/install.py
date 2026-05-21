#!/usr/bin/env python3
"""Install or uninstall the plexctl CLI symlink.

Usage:
    python scripts/install.py install     # Create symlink (default)
    python scripts/install.py uninstall   # Remove symlink
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_PREFIX = Path(os.environ.get("HOME", "~")) / ".local"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_DIR / "bin" / "plexctl"


def install(prefix: Path = DEFAULT_PREFIX) -> None:
    """Create a symlink from PREFIX/bin/plexctl pointing to the project's bin/plexctl."""
    link_path = prefix / "bin" / "plexctl"

    if link_path.is_symlink() and link_path.resolve() == SOURCE.resolve():
        print(f"Already installed: {link_path} -> {SOURCE}")
        return

    link_path.parent.mkdir(parents=True, exist_ok=True)

    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()

    link_path.symlink_to(SOURCE)
    print(f"Installed plexctl -> {link_path}")


def uninstall(prefix: Path = DEFAULT_PREFIX) -> None:
    """Remove the plexctl symlink from PREFIX/bin."""
    link_path = prefix / "bin" / "plexctl"

    if not link_path.exists() and not link_path.is_symlink():
        print(f"plexctl not found at {link_path}")
        return

    link_path.unlink()
    print("Uninstalled plexctl")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] == "install":
        install()
    elif sys.argv[1] == "uninstall":
        uninstall()
    else:
        print(f"Unknown command: {sys.argv[1]}", file=sys.stderr)
        print("Usage: python scripts/install.py [install|uninstall]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()