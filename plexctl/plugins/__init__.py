"""Plugin system for plexctl.

Plugins extend plexctl with external integrations that are not
part of the core Plex API. Each plugin is a self-contained package
under plexctl/plugins/ that provides its own client, service,
configuration, and CLI commands.

To create a plugin:
1. Create a package directory under plexctl/plugins/<name>/
2. Subclass Plugin in __init__.py
3. Implement the required abstract methods
4. The plugin registry discovers and loads it automatically.
"""
