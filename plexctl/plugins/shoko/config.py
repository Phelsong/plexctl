"""Shoko plugin configuration.

Provides ShokoConfig and load_shoko_config for connecting to a Shoko Server.
Follows the same priority order as core plexctl configuration:
env vars > .env file > TOML config > defaults.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ShokoConfig(BaseSettings):
    """Connection settings for the Shoko Server API.

    Set SHOKO_URL and SHOKO_KEY as environment variables, or
    place them in ~/config/plexctl/plexctl.toml under [shoko].
    A legacy .env file in the working directory is also checked.

    Attributes:
        url: Base URL of the Shoko server (e.g. http://localhost:8111).
        apikey: Shoko API key for authentication.
        timeout: Request timeout in seconds.
        media_root: Root path for media files on the server filesystem.
    """

    model_config = SettingsConfigDict(
        env_prefix="SHOKO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    url: str = Field(default="http://localhost:8111", description="Shoko server URL")
    apikey: str = Field(
        default="",
        alias="SHOKO_KEY",
        description="Shoko API key",
    )
    timeout: int = Field(default=30, description="Request timeout in seconds")
    media_root: str = Field(
        default="/mnt/nfs/media",
        alias="SHOKO_MEDIA_ROOT",
        description="Root path for media files on server filesystem",
    )

    def is_valid(self) -> bool:
        """Check if the config has required values set."""
        return bool(self.url and self.apikey)


def load_shoko_config(env_path=None):
    """Load Shoko configuration from plexctl.toml, env vars, or .env file.

    Configuration is loaded in priority order:
    1. Environment variables (SHOKO_URL, SHOKO_KEY, etc.)
    2. .env file in the working directory (legacy)
    3. ~/config/plexctl/plexctl.toml [shoko] section
    4. Built-in defaults

    Args:
        env_path: Optional path to a legacy .env file.

    Returns:
        Validated ShokoConfig instance.
    """
    import warnings

    from plexctl.config import _load_toml_overrides, config_path

    conf_file = config_path()

    # Check permissions
    if conf_file.exists():
        import stat

        mode = conf_file.stat().st_mode
        if mode & 0o070 or mode & 0o007:
            octal = stat.S_IMODE(mode)
            warnings.warn(
                f"Config file {conf_file} has permissions {oct(octal)} — "
                f"API tokens may be visible to other users. "
                f"Fix with: chmod 400 {conf_file}",
                stacklevel=3,
            )

    # Read TOML
    toml_data: dict = {}
    if conf_file.exists():
        import tomllib

        try:
            with open(conf_file, "rb") as fh:
                toml_data = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            warnings.warn(
                f"Could not read config file {conf_file}: {exc}",
                stacklevel=3,
            )

    # Shoko env var names don't follow the standard pattern:
    #   apikey -> SHOKO_KEY (not SHOKO_APIKEY)
    #   media_root -> SHOKO_MEDIA_ROOT
    alias_map = {"apikey": "KEY", "media_root": "MEDIA_ROOT"}

    overrides = _load_toml_overrides(
        toml_data,
        section="shoko",
        env_prefix="SHOKO_",
        field_names=("url", "apikey", "timeout", "media_root"),
        alias_map=alias_map,
    )

    if env_path is not None:
        return ShokoConfig(_env_file=env_path, **overrides)  # type: ignore[call-arg]
    return ShokoConfig(**overrides)
