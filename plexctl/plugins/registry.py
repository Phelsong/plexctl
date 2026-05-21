"""Plugin registry for discovering and loading plexctl plugins.

Scans plexctl/plugins/ for subpackages containing Plugin subclasses,
validates them, and registers their CLI apps with the main typer app.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typer

from plexctl.plugins.protocol import Plugin

logger = logging.getLogger(__name__)

_registry: PluginRegistry | None = None


class PluginRegistry:
    """Discovers, validates, and registers plugins with the CLI app.

    Plugins are discovered by scanning subpackages of plexctl.plugins.
    Each subpackage's __init__.py module is inspected for a Plugin subclass.
    Valid plugins are instantiated and their CLI apps registered with typer.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    @property
    def plugins(self) -> dict[str, Plugin]:
        """Return mapping of plugin name to plugin instance."""
        return dict(self._plugins)

    def register(self, app: typer.Typer, plugin: Plugin) -> None:
        """Register a single plugin's CLI app with the main typer app.

        Args:
            app: Main typer.Typer application.
            plugin: Validated plugin instance.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        if plugin.name in self._plugins:
            msg = f"Plugin '{plugin.name}' is already registered"
            raise ValueError(msg)

        cli_app = plugin.create_cli_app()
        app.add_typer(cli_app, name=plugin.name)
        self._plugins[plugin.name] = plugin
        logger.info("Registered plugin: %s", plugin.name)

    def get_plugin(self, name: str) -> Plugin | None:
        """Look up a registered plugin by name.

        Args:
            name: Plugin identifier (e.g. 'shoko').

        Returns:
            Plugin instance if found, None otherwise.
        """
        return self._plugins.get(name)


def _scan_plugin_packages() -> list[str]:
    """Find all subpackages under plexctl.plugins.

    Returns:
        List of fully-qualified module names (e.g. ['plexctl.plugins.shoko']).
    """
    import plexctl.plugins as plugins_pkg

    package_path = plugins_pkg.__path__
    return [
        f"plexctl.plugins.{name}"
        for _, name, is_pkg in pkgutil.iter_modules(package_path)
        if is_pkg
    ]


def discover_plugins() -> list[type[Plugin]]:
    """Discover Plugin subclasses from plexctl.plugins subpackages.

    Scans each subpackage's __init__.py for a concrete Plugin subclass.
    Skips packages that don't contain a valid plugin.

    Returns:
        List of Plugin subclass types ready for instantiation.
    """
    plugin_classes: list[type[Plugin]] = []

    for module_name in _scan_plugin_packages():
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            logger.warning("Failed to import plugin package: %s", module_name)
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Plugin)
                and attr is not Plugin
            ):
                plugin_classes.append(attr)
                logger.debug("Found plugin class: %s in %s", attr.__name__, module_name)

    return plugin_classes


def register_plugins(app: typer.Typer) -> PluginRegistry:
    """Discover all plugins and register their CLI apps.

    This is the main entry point called from cli.py during startup.
    It discovers plugin classes, instantiates them, validates their
    contracts, and registers their CLI sub-apps.

    Args:
        app: Main typer.Typer application.

    Returns:
        PluginRegistry with all discovered plugins registered.
    """
    global _registry

    registry = PluginRegistry()

    for plugin_class in discover_plugins():
        try:
            plugin = plugin_class()
            registry.register(app, plugin)
        except (ValueError, TypeError) as exc:
            logger.error("Failed to register plugin %s: %s", plugin_class.__name__, exc)

    _registry = registry
    return registry


def get_registry() -> PluginRegistry:
    """Return the global plugin registry.

    Returns:
        The PluginRegistry populated during startup.

    Raises:
        RuntimeError: If plugins have not been registered yet.
    """
    if _registry is None:
        msg = "Plugin registry not initialized. Call register_plugins() first."
        raise RuntimeError(msg)
    return _registry
