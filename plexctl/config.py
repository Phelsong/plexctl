"""Configuration management for plexctl.

Reads connection settings from a TOML config file at
$XDG_CONFIG_HOME/plexctl/plexctl.toml (defaults to
~/.config/plexctl/plexctl.toml). Environment variables and
legacy .env files in the working directory are also supported
for backward compatibility.

For security, the config file should be readable only by the
owner (mode 0o400 or 0o600). A warning is printed if the file
has overly permissive permissions since it contains API tokens.

Config file format (TOML):

    [plex]
    url = "https://plex.example.com"
    token = "your-plex-token"

    [shoko]
    url = "https://shoko.example.com"
    apikey = "your-shoko-apikey"
    media_root = "/mnt/nfs/media/anime"
"""

from __future__ import annotations

import os
import stat
import tomllib
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typer import get_app_dir


@lru_cache(maxsize=1)
def config_dir() -> Path:
    """Return the plexctl OS-default config directory."""
    return Path(get_app_dir("plexctl"))


@lru_cache(maxsize=1)
def config_path() -> Path:
    """Return the path to plexctl.toml."""
    config_path: Path = Path(config_dir()) / "plexctl.toml"
    return config_path


def _check_permissions(path: Path) -> None:
    """Warn if the config file has overly permissive permissions.

    The config file contains sensitive API tokens and should only
    be readable by the owner. Acceptable modes are 0o400 (read-only
    owner) and 0o600 (owner read-write). Any other mode triggers
    a warning.
    """
    if not path.exists():
        return

    mode = path.stat().st_mode
    group_bits = mode & 0o070
    other_bits = mode & 0o007

    if group_bits or other_bits:
        octal = stat.S_IMODE(mode)
        warnings.warn(
            f"Config file {path} has permissions {oct(octal)} — "
            f"API tokens may be visible to other users. "
            f"Fix with: chmod 400 {path}",
            stacklevel=3,
        )


@lru_cache(maxsize=1)
def _read_toml_config(path: Path) -> dict[str, Any]:
    """Parse a TOML config file and return its sections.

    Returns an empty dict if the file does not exist or cannot
    be read.
    """
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        warnings.warn(f"Could not read config file {path}: {exc}", stacklevel=3)
        return {}


class PlexConfig(BaseSettings):
    """Connection settings for the Plex server.

    Set PLEX_URL and PLEX_TOKEN as environment variables, or
    place them in ~/config/plexctl/plexctl.toml under [plex].
    A .env file in the working directory is also checked (primarily for development overide).

    Attributes:
        url: Base URL of the Plex server (e.g. http://localhost:32400).
        token: Plex authentication token from plex.tv.
        timeout: Request timeout in seconds.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLEX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    url: str = Field(default="http://localhost:32400", description="Plex server URL")
    token: str = Field(default="", description="Plex authentication token")
    timeout: int = Field(default=30, description="Request timeout in seconds")

    def is_valid(self) -> bool:
        """Check if the config has required values set."""
        return bool(self.url and self.token)


def _load_toml_overrides(
    toml_data: dict[str, Any],
    section: str,
    env_prefix: str,
    field_names: tuple[str, ...],
    alias_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract TOML values NOT already provided by environment variables.

    For each field in the TOML section, check if the corresponding
    environment variable is set. If not, include the TOML value so
    it can be passed as an init kwarg. This ensures environment
    variables always take priority over TOML file values.

    Args:
        toml_data: Parsed TOML data with top-level sections.
        section: TOML section name (e.g. "plex", "shoko").
        env_prefix: Environment variable prefix (e.g. "PLEX_", "SHOKO_").
        field_names: Public field names to look up in the TOML section.
        alias_map: Map from public field name to env var suffix
            (e.g. {"apikey": "KEY"} for SHOKO_KEY).

    Returns:
        Dict of init kwargs for values not already set by env vars.
    """
    toml_section = toml_data.get(section, {})
    if not toml_section:
        return {}

    alias_map = alias_map or {}
    overrides: dict[str, Any] = {}

    for field_name in field_names:
        if field_name not in toml_section:
            continue

        # Determine the env var name: alias_map overrides the default
        # mapping (e.g. "apikey" → "SHOKO_KEY" not "SHOKO_APIKEY").
        env_suffix = alias_map.get(field_name, field_name.upper())
        env_var_name = f"{env_prefix}{env_suffix}"

        # Only inject TOML value when the env var is NOT set,
        # so env vars always win.
        if env_var_name not in os.environ:
            overrides[field_name] = toml_section[field_name]

    return overrides


def load_config(env_path: Path | None = None) -> PlexConfig:
    """Load Plex configuration from plexctl.toml, env vars, or .env file.

    Configuration is loaded in priority order:
    1. Environment variables (PLEX_URL, PLEX_TOKEN, etc.)
    2. .env file in the working directory (legacy)
    3. ~/config/plexctl/plexctl.toml [plex] section
    4. Built-in defaults

    Args:
        env_path: Optional path to a legacy .env file.

    Returns:
        Validated PlexConfig instance.
    """
    conf_file = config_path()
    _check_permissions(conf_file)
    toml_data = _read_toml_config(conf_file)

    # Pass TOML values as init kwargs ONLY when the corresponding
    # env var is not set. This preserves the env > dotenv > TOML
    # priority order.
    overrides = _load_toml_overrides(
        toml_data, section="plex", env_prefix="PLEX_", field_names=("url", "token", "timeout")
    )

    if env_path is not None:
        return PlexConfig(_env_file=env_path, **overrides)  # type: ignore[call-arg]
    return PlexConfig(**overrides)
