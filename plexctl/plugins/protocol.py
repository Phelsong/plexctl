"""Plugin protocol defining the contract for plexctl plugins.

Every plugin must subclass Plugin and implement all abstract methods.
The plugin registry validates these at discovery time, failing fast
if the contract is not met.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    import typer
    from pydantic_settings import BaseSettings


class Plugin(ABC):
    """Base class for all plexctl plugins.

    A plugin encapsulates an external integration: its own configuration,
    HTTP client, service layer, and CLI commands. Plugins are discovered
    automatically from plexctl/plugins/ subpackages by the PluginRegistry.

    Subclasses must set these ClassVar attributes:
        name: Unique identifier used as the CLI subcommand name.
        help_text: Short description shown in CLI help.
        config_class: Pydantic BaseSettings subclass for plugin configuration.

    And implement these methods:
        create_cli_app: Build the typer sub-app with all plugin commands.
        create_service: Build the service from a loaded config instance.
        load_config: Load and validate configuration from env/TOML/defaults.
    """

    name: ClassVar[str]
    help_text: ClassVar[str]
    config_class: ClassVar[type[BaseSettings]]

    @abstractmethod
    def create_cli_app(self) -> typer.Typer:
        """Build and return the typer sub-app for this plugin's CLI commands.

        Returns:
            Configured typer.Typer instance with all plugin commands registered.
        """

    @abstractmethod
    def create_service(self, config: BaseSettings) -> Any:
        """Build the service instance from a validated config.

        Args:
            config: Loaded and validated configuration instance.

        Returns:
            Plugin-specific service instance.
        """

    @abstractmethod
    def load_config(self) -> BaseSettings:
        """Load and validate plugin configuration.

        Reads from environment variables, TOML config, .env files,
        and built-in defaults — following the same priority order
        as core plexctl configuration.

        Returns:
            Validated configuration instance of the plugin's config_class.
        """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate that subclasses define all required ClassVar attributes."""
        super().__init_subclass__(**kwargs)
        required_attrs = ("name", "help_text", "config_class")
        missing = [attr for attr in required_attrs if not hasattr(cls, attr)]
        if missing:
            msg = (
                f"Plugin subclass {cls.__name__} is missing required "
                f"class attributes: {', '.join(missing)}"
            )
            raise TypeError(msg)
