#!/usr/bin/env python3
"""Generate a command tree document for plexctl CLI.

This script introspects the Typer app structure and generates a markdown
document listing all active (non-deprecated) commands with descriptions.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Any

import typer.models
from plexctl.cli import app

# Groups that appear at the top level but are canonical aliases of
# sub-groups under other commands.  The canonical path should be used
# instead, so we skip them from the command reference.
_DEPRECATED_TOP_LEVEL_GROUPS: frozenset[str] = frozenset(
    {"collections"}  # canonical: library collections
)

# The DefaultPlaceholder sentinel Typer uses for "not set" values.
_DUMMY = typer.models.DefaultPlaceholder


def _unwrap_placeholder(value: object) -> object:
    """Return the real value if *value* is a Typer DefaultPlaceholder."""
    if isinstance(value, _DUMMY):
        return value.value
    return value


def is_deprecated(group_or_command: Any) -> bool:
    """Return True if the Typer group or command is marked deprecated.

    For groups, checks both ``group_info.deprecated`` and
    ``typer_instance.info.deprecated``.  For commands, checks
    ``cmd.deprecated``.
    """
    # TyperGroup on the main app
    if hasattr(group_or_command, "deprecated") and group_or_command.deprecated is True:
        return True

    # Typer instance's info object
    info = getattr(group_or_command, "info", None)
    if info:
        dep = _unwrap_placeholder(getattr(info, "deprecated", False))
        if dep is True:
            return True

    return False


def _humanize_command_name(name: str) -> str:
    """Convert a kebab-case command name into a short human description.

    Used as a fallback when no help text is available (e.g. for
    dynamically-generated tag commands).
    """
    # e.g. "add-genre" → "Add genre"
    parts = name.replace("-", " ").split()
    if not parts:
        return ""
    verb = parts[0].capitalize()
    rest = " ".join(parts[1:])
    if rest:
        return f"{verb} {rest}"
    return verb


def get_command_help(command: Any) -> str:
    """Extract the first line of help text from a Typer command.

    Typer stores help either on ``command.help`` (when set via the
    decorator) or on the callback function's ``__doc__``.  Falls back
    to a humanized version of the command name when neither is available.
    """
    help_text = command.help
    if help_text is None:
        callback = command.callback
        if callback and callback.__doc__:
            help_text = callback.__doc__
    if help_text is None:
        # Dynamic commands (e.g. tag add/remove) may lack docstrings.
        # Fall back to a human-readable name.
        cmd_name = getattr(command, "name", None)
        if cmd_name:
            return _humanize_command_name(cmd_name)
        return ""
    first_line = help_text.strip().split("\n")[0]
    # Remove template placeholders like {display_name} that weren't
    # evaluated in closure docstrings.
    if "{" in first_line:
        cmd_name = getattr(command, "name", None)
        if cmd_name:
            return _humanize_command_name(cmd_name)
    return first_line


def get_group_help(typer_instance: Any) -> str:
    """Extract the first line of help text from a Typer app/group."""
    info = getattr(typer_instance, "info", None)
    if info:
        help_text = _unwrap_placeholder(info.help) or ""
        if help_text:
            return str(help_text).split("\n")[0]
    return ""


def _format_commands(commands: list[Any], group_name: str, indent: str) -> list[str]:
    """Format a list of registered Typer commands as markdown list items."""
    lines: list[str] = []
    for cmd in commands:
        cmd_name = cmd.name
        # Skip anonymous callback-commands (used by invoke_without_command)
        if cmd_name is None:
            continue
        # Skip deprecated commands
        if cmd.deprecated:
            continue
        help_line = get_command_help(cmd)
        if help_line:
            lines.append(f"{indent}- **`{group_name} {cmd_name}`** — {help_line}")
        else:
            lines.append(f"{indent}- **`{group_name} {cmd_name}`**")
    return lines


def _format_sub_groups(sub_groups: list[Any], group_name: str, indent: str) -> list[str]:
    """Format a list of registered Typer sub-groups recursively."""
    lines: list[str] = []
    for sub_group in sub_groups:
        sub_name = sub_group.name
        sub_typer = sub_group.typer_instance

        # Skip deprecated sub-groups
        if is_deprecated(sub_typer) or getattr(sub_group, "deprecated", False):
            continue

        sub_help = get_group_help(sub_typer)
        if sub_help:
            lines.append(f"{indent}- **`{group_name} {sub_name}`** — {sub_help}")
        else:
            lines.append(f"{indent}- **`{group_name} {sub_name}`**")

        child_name = f"{group_name} {sub_name}"
        child_indent = f"{indent}  "

        # Sub-commands
        sub_commands = sub_typer.registered_commands
        cmd_lines = _format_commands(sub_commands, child_name, child_indent)
        lines.extend(cmd_lines)

        # Nested sub-groups (e.g. smart under playlists)
        sub_sub_groups = sub_typer.registered_groups
        if sub_sub_groups:
            sub_sub_lines = _format_sub_groups(sub_sub_groups, child_name, child_indent)
            lines.extend(sub_sub_lines)

    return lines


def generate_tree() -> str:
    """Generate the command tree markdown."""
    lines: list[str] = []
    lines.append("# plexctl Command Reference")
    lines.append("")
    lines.append("Auto-generated command tree for plexctl.")
    lines.append("This document lists all active (non-deprecated) commands.")
    lines.append("")

    registered_groups = app.registered_groups
    command_count = 0

    for group_info in registered_groups:
        name = group_info.name
        typer_instance = group_info.typer_instance

        # Skip deprecated top-level groups
        if is_deprecated(group_info) or is_deprecated(typer_instance):
            continue

        # Skip known deprecated alias groups
        if name in _DEPRECATED_TOP_LEVEL_GROUPS:
            continue

        help_line = get_group_help(typer_instance)
        lines.append(f"## `{name}`")
        if help_line:
            lines.append(f"\n{help_line}\n")
        else:
            lines.append("")

        # Regular commands
        commands = typer_instance.registered_commands
        sub_groups = typer_instance.registered_groups
        has_subcommands = bool(commands) or bool(sub_groups)

        # Handle the default callback for groups with invoke_without_command.
        # These groups act as both a group and a command.  When they have
        # sub-commands we show it as the first entry (the "default" action);
        # when they have NO sub-commands (like `movies`) we show it as the
        # sole entry under the heading.
        registered_callback = getattr(typer_instance, "registered_callback", None)
        if registered_callback and registered_callback.callback:
            cb_doc = (registered_callback.callback.__doc__ or "").strip()
            cb_help = cb_doc.split("\n")[0] if cb_doc else ""
            if has_subcommands:
                # Show the default action first, before sub-commands
                if cb_help:
                    lines.append(f"- **`{name}`** *(default)* — {cb_help}")
                else:
                    lines.append(f"- **`{name}`** *(default)*")
                command_count += 1
            elif not has_subcommands:
                # Group with ONLY a callback (e.g. `movies`) — show as
                # the sole command entry
                if cb_help:
                    lines.append(f"- **`{name}`** — {cb_help}")
                else:
                    lines.append(f"- **`{name}`**")
                command_count += 1

        cmd_lines = _format_commands(commands, name, "")
        lines.extend(cmd_lines)
        command_count += sum(1 for line in cmd_lines if line.startswith("- **`"))

        # Sub-groups (e.g. library collections, library playlists)
        if sub_groups:
            sub_lines = _format_sub_groups(sub_groups, name, "")
            lines.extend(sub_lines)
            command_count += sum(1 for line in sub_lines if line.startswith("- **`"))

        lines.append("")

    lines.append("---")
    lines.append(f"*Total active commands: {command_count}*")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Write the generated command tree to the docs directory."""
    output_path = Path(__file__).resolve().parent.parent / "docs" / "command_tree.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tree = generate_tree()
    output_path.write_text(tree)

    # Count command entries (lines starting with "- **`")
    count = sum(1 for line in tree.split("\n") if line.startswith("- **`"))
    print(f"Generated command tree with {count} commands → {output_path}")


if __name__ == "__main__":
    main()
