"""Shoko plugin for plexctl.

Integrates the Shoko anime metadata server with plexctl, providing
commands for querying series, episodes, files, TMDB links, CRC
auditing, and .plexmatch generation.

This plugin encapsulates all Shoko-specific functionality:
- Configuration (ShokoConfig)
- HTTP client (ShokoClient)
- Service layer (ShokoService)
- CLI commands (shoko_app)
- CSV converters
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import typer
    from pydantic_settings import BaseSettings

from plexctl.plugins.protocol import Plugin
from plexctl.plugins.shoko.commands import shoko_app
from plexctl.plugins.shoko.config import ShokoConfig, load_shoko_config
from plexctl.plugins.shoko.service import ShokoService


class ShokoPlugin(Plugin):
    """Plugin integrating Shoko Server with plexctl.

    Provides CLI commands for querying Shoko's anime metadata API,
    managing TMDB links, auditing CRC hashes, and generating
    .plexmatch files for Plex.
    """

    name: ClassVar[str] = "shoko"
    help_text: ClassVar[str] = "Query Shoko Server for anime metadata and file info."
    config_class: ClassVar[type[BaseSettings]] = ShokoConfig

    def create_cli_app(self) -> typer.Typer:
        """Return the Shoko CLI sub-app with all commands registered."""
        return shoko_app

    def create_service(self, config: BaseSettings) -> ShokoService:
        """Create a ShokoService from a validated ShokoConfig."""
        from plexctl.plugins.shoko.client import ShokoClient

        if not isinstance(config, ShokoConfig):
            msg = f"Expected ShokoConfig, got {type(config).__name__}"
            raise TypeError(msg)

        client = ShokoClient(config)
        return ShokoService(client)

    def load_config(self) -> ShokoConfig:
        """Load Shoko configuration from env vars, .env, or TOML."""
        return load_shoko_config()


__all__ = ["ShokoConfig", "ShokoPlugin", "ShokoService", "load_shoko_config"]
