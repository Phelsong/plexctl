"""Shared Typer option definitions for CSV output.

Provides a consistent --csv and --output option pair across all commands.
When --csv is set, command output goes to CSV instead of Rich tables.
"""

from typing import Annotated

import typer

CsvFlag = Annotated[
    bool,
    typer.Option(
        "--csv",
        help="Output results as CSV instead of formatted tables.",
    ),
]

OutputFile = Annotated[
    str | None,
    typer.Option(
        "--output",
        "-o",
        help="Write output to this file path instead of stdout.",
    ),
]
