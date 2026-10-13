"""Tests for the pinned-table feature (plexctl.pin)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import types
from typing import TYPE_CHECKING

import pytest
import typer
from plexctl.pin import (
    _MIN_COLUMN_WIDTH,
    _NO_REPRINT_ENV,
    _fit_column_widths,
    _replay_args,
    _truncate_cell,
    capture_csv,
    clear_pin,
    command_source,
    load_last_command,
    load_pin,
    pin_last_command,
    print_pin,
    record_command_run,
    register_pin,
    render_pin,
    save_pin,
    stash_last_output,
)
from rich.console import Console
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch

CSV_MOVIES = "title,year\nFight Club,1999\nAlien,1979\n"


def _capture_console(monkeypatch: MonkeyPatch) -> io.StringIO:
    """Point the pin module's console at a buffer and return it."""
    buffer = io.StringIO()
    monkeypatch.setattr(
        "plexctl.pin.console", Console(file=buffer, width=120, force_terminal=False)
    )
    return buffer


@pytest.fixture
def pin_env(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """Isolate all pin state to a temporary config directory."""
    monkeypatch.setattr("plexctl.pin.config_dir", lambda: tmp_path)
    return tmp_path


def _stash_state(pin_env: Path) -> dict[str, str]:
    """Read the persisted CSV stash ({source, csv})."""
    data = json.loads((pin_env / "last_output.json").read_text())
    return {"source": data.get("source", ""), "csv": data.get("csv", "")}


def _fake_run(
    monkeypatch: MonkeyPatch,
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    raises: Exception | None = None,
) -> dict[str, object]:
    """Replace subprocess.run with a stub recording how the child was called."""
    calls: dict[str, object] = {}

    def run(cmd: list[str], **kwargs: object) -> types.SimpleNamespace:
        calls["cmd"] = list(cmd)
        calls["timeout"] = kwargs.get("timeout")
        calls["env"] = kwargs.get("env")
        if raises is not None:
            raise raises
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _build_app() -> typer.Typer:
    """Build a minimal fresh app with one command and the pin feature."""
    app = typer.Typer()

    @app.command()
    def hello() -> None:
        """Print a known token for tests to find."""
        typer.echo("HELLO_TOKEN")

    register_pin(app)
    return app


def _build_csv_app() -> typer.Typer:
    """Minimal app whose leaf command supports --csv (no side effects)."""
    app = typer.Typer()

    @app.command()
    def rows(csv: bool = typer.Option(False, "--csv")) -> None:
        """Plain table normally; the CSV run stashes tabular output upstream."""
        if csv:
            typer.echo("title,year")
        else:
            typer.echo("ROWS_TABLE")

    register_pin(app)
    return app


class TestCaptureCsv:
    """Test capturing CSV text into the pin store."""

    def test_roundtrip(self, pin_env: Path) -> None:
        """Captured CSV pins both rows and renders back as a table."""
        assert capture_csv(CSV_MOVIES, "plexctl movies list") == 2

        pin = load_pin()
        assert pin is not None
        assert pin["source"] == "plexctl movies list"

        table = render_pin()
        assert table is not None
        rendered = io.StringIO()
        Console(file=rendered, width=120).print(table)
        text = rendered.getvalue()
        assert "Fight Club" in text
        assert "1999" in text

    def test_print_pin_outputs_table(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """print_pin renders the pinned values to the console."""
        capture_csv(CSV_MOVIES, "plexctl movies list")
        buffer = _capture_console(monkeypatch)
        print_pin()
        output = buffer.getvalue()
        assert "Fight Club" in output
        assert "Alien" in output

    def test_empty_csv_raises(self, pin_env: Path) -> None:
        """Empty input has nothing tabular to pin."""
        with pytest.raises(ValueError, match="no tabular output to pin"):
            capture_csv("", "plexctl movies list")
        assert load_pin() is None  # failed capture must not persist state

    def test_headers_only_csv_raises(self, pin_env: Path) -> None:
        """Header-only CSV has no rows to pin."""
        with pytest.raises(ValueError, match="produced no rows to pin"):
            capture_csv("only,headers\n", "plexctl movies list")
        assert load_pin() is None


class TestCellTruncation:
    """Pinned cells collapse whitespace and clip long text to one line."""

    def test_collapse_whitespace(self) -> None:
        """Newlines, tabs and padding collapse into single spaces."""
        assert _truncate_cell("a\nb   c\td") == "a b c d"

    def test_short_value_untouched(self) -> None:
        """Values under the limit pass through unchanged."""
        assert _truncate_cell("ok") == "ok"
        assert _truncate_cell("x" * 72) == "x" * 72

    def test_clip_long_value_with_ellipsis(self) -> None:
        """Values over the limit are cut to the limit with an ellipsis."""
        out = _truncate_cell("x" * 200)
        assert out == "x" * 71 + "…"
        assert len(out) == 72

    def test_long_summary_single_line(self, pin_env: Path) -> None:
        """A paragraph-length summary renders once, clipped, not folded."""
        summary = "Explores the high-pressure experiences of police. " * 6
        save_pin(["title", "summary"], [{"title": "9-1-1", "summary": summary}], "plexctl shows")

        table = render_pin()
        assert table is not None
        rendered = io.StringIO()
        Console(file=rendered, width=200).print(table)
        text = rendered.getvalue()

        assert "…" in text
        assert summary.strip() not in text
        # one line per record: title, header, rule and a single data line
        assert len(text.rstrip().split("\n")) <= 6
        # every rendered row fits the console width the table was fitted to
        assert max(len(line) for line in text.splitlines()) <= 82

    def test_summary_column_renders_clipped_value(
        self, pin_env: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """The clipped summary starts with the cell's opening words."""
        summary = "Explores the high-pressure experiences of police. " * 6
        save_pin(["summary"], [{"summary": summary}], "plexctl shows")
        buffer = _capture_console(monkeypatch)
        print_pin()
        output = buffer.getvalue()
        assert "Explores the high-pressure experiences of police." in output
        assert summary.strip() not in output


class TestColumnFitting:
    """Column widths are fitted to the console so rows stay single-line."""

    def test_no_shrink_when_natural_fits(self) -> None:
        """Content narrower than the console keeps its natural widths."""
        assert _fit_column_widths([5, 10, 4], 100) == [5, 10, 4]

    def test_widest_column_absorbs_overflow(self) -> None:
        """Wide columns shrink; narrow data columns keep their size."""
        widths = _fit_column_widths([5, 100], 50)
        assert sum(widths) <= 50
        assert widths[0] == 5  # narrow column untouched
        assert widths[1] == 45

    def test_minimum_width_respected(self) -> None:
        """No column shrinks below the floor."""
        widths = _fit_column_widths([6, 200], 20)
        assert sum(widths) <= 20
        assert min(widths) >= _MIN_COLUMN_WIDTH

    def test_too_narrow_terminal_keeps_natural(self) -> None:
        """Below minimum total width, degrade instead of crushing columns."""
        natural = [50, 50]
        assert _fit_column_widths(natural, 8) == natural


class TestClearPin:
    """Test removing the pin."""

    def test_clear_removes_pin(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """After clear_pin, nothing is pinned and nothing prints."""
        capture_csv(CSV_MOVIES, "plexctl movies list")

        assert clear_pin() is True
        assert load_pin() is None

        buffer = _capture_console(monkeypatch)
        print_pin()
        assert buffer.getvalue() == ""

    def test_clear_without_pin(self, pin_env: Path) -> None:
        """Clearing when nothing is pinned reports False."""
        assert clear_pin() is False


class TestRecordCommandRun:
    """Recording completed commands for pin's background replay."""

    def test_regular_command_recorded(self, pin_env: Path) -> None:
        """A regular command's argv tokens persist verbatim."""
        record_command_run(["server", "info", "--json"])
        assert load_last_command() == ["server", "info", "--json"]

    def test_meta_commands_skipped(self, pin_env: Path) -> None:
        """pin/unpin/repl/help never retarget the recorded command."""
        record_command_run(["movies", "list"])
        for meta in ("pin", "unpin", "repl", "help"):
            record_command_run([meta, "--extra"])
        assert load_last_command() == ["movies", "list"]

    def test_option_tokens_skipped(self, pin_env: Path) -> None:
        """Tokens that start with '-' are not command positions."""
        record_command_run(["--help"])
        assert load_last_command() is None

    def test_non_csv_run_clears_stash(self, pin_env: Path) -> None:
        """A plain-table run blots stale CSV so pin replays it later."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        record_command_run(["server", "info"])
        assert _stash_state(pin_env)["csv"] == ""
        assert load_last_command() == ["server", "info"]

    def test_failed_run_clears_stash(self, pin_env: Path) -> None:
        """A failed --csv run must not leave a stale stash behind."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        record_command_run(["movies", "search", "--csv"], failed=True)
        assert _stash_state(pin_env)["csv"] == ""
        assert load_last_command() == ["movies", "search", "--csv"]

    def test_csv_run_keeps_stash(self, pin_env: Path) -> None:
        """A stdout-CSV run keeps its freshly stashed CSV for the fast path."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        record_command_run(["movies", "list", "--csv"])
        assert _stash_state(pin_env)["csv"] == CSV_MOVIES
        assert load_last_command() == ["movies", "list", "--csv"]

    def test_output_redirect_clears_stash(self, pin_env: Path) -> None:
        """--output runs write to a file, so they don't refresh the stash."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        record_command_run(["rows", "--csv", "--output", "shows.csv"])
        assert _stash_state(pin_env)["csv"] == ""


class TestReplayArgs:
    """Token normalization for the background re-run."""

    def test_appends_csv_once(self, pin_env: Path) -> None:
        """Plain tokens gain a single trailing --csv."""
        assert _replay_args(["movies", "list"]) == ["movies", "list", "--csv"]

    def test_keeps_existing_csv(self, pin_env: Path) -> None:
        """An --csv already in the tokens is not duplicated."""
        assert _replay_args(["shows", "list", "--csv"]) == ["shows", "list", "--csv"]

    def test_drops_output_flag_with_value(self, pin_env: Path) -> None:
        """--output/-o redirections (and their values) are not replayed."""
        assert _replay_args(["movies", "list", "--output", "f.csv", "--csv"]) == [
            "movies",
            "list",
            "--csv",
        ]
        assert _replay_args(["movies", "list", "-o", "f.csv"]) == ["movies", "list", "--csv"]

    def test_drops_inline_output(self, pin_env: Path) -> None:
        """--output=value form is dropped too."""
        assert _replay_args(["movies", "list", "--output=f.csv"]) == ["movies", "list", "--csv"]


class TestPinLastCommand:
    """Pin the last command: direct fast path and background replay."""

    def test_direct_pin_from_stash(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """A --csv run with a fresh stash pins instantly, no child process."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        record_command_run(["movies", "list", "--csv"])
        _fake_run(monkeypatch, raises=AssertionError("child must not be spawned"))

        rows, source, replayed = pin_last_command(_build_csv_app())
        assert rows == 2
        assert source == "plexctl movies list"
        assert replayed is False
        assert load_pin() is not None and load_pin()["source"] == source

    def test_replay_pins_recorded_command(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """A plain-table last command is re-run with --csv in the background."""
        record_command_run(["rows"])
        calls = _fake_run(monkeypatch, stdout=CSV_MOVIES)

        rows, source, replayed = pin_last_command(_build_csv_app())
        assert rows == 2
        assert source == "plexctl rows"
        assert replayed is True
        assert load_pin() is not None and load_pin()["source"] == source
        expected = [sys.executable, "-m", "plexctl", "rows", "--csv"]
        assert calls["cmd"] == expected
        assert calls["env"] is not None
        assert _NO_REPRINT_ENV in calls["env"]

    def test_replay_strips_output_flag(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """--output redirections aren't replayed; the child writes to stdout."""
        record_command_run(["rows", "--csv", "--output", "shows.csv"])
        calls = _fake_run(monkeypatch, stdout=CSV_MOVIES)

        rows, _, replayed = pin_last_command(_build_csv_app())
        assert rows == 2
        assert replayed is True
        assert "--output" not in calls["cmd"]
        assert "shows.csv" not in calls["cmd"]

    def test_replay_failure_reports_error(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """A failing child surfaces its last error line and pins nothing."""
        record_command_run(["rows"])
        _fake_run(monkeypatch, returncode=2, stderr="Error: server unreachable")

        with pytest.raises(ValueError, match=r"background re-run of .* failed"):
            pin_last_command(_build_csv_app())
        assert load_pin() is None

    def test_replay_timeout_reports_error(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """A hung child surfaces the timeout instead of hanging forever."""
        record_command_run(["rows"])
        _fake_run(monkeypatch, raises=subprocess.TimeoutExpired(cmd=["plexctl"], timeout=120))

        with pytest.raises(ValueError, match="timed out"):
            pin_last_command(_build_csv_app())
        assert load_pin() is None

    def test_unsupported_command_refused(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """Commands w/o --csv (mutating commands) are never re-run."""
        record_command_run(["hello"])
        _fake_run(monkeypatch, raises=AssertionError("child must not be spawned"))

        with pytest.raises(ValueError, match="does not support --csv"):
            pin_last_command(_build_app())
        assert load_pin() is None
        assert load_last_command() == ["hello"]

    def test_no_history_reports_error(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """With nothing recorded and no stash there's nothing to pin."""
        _fake_run(monkeypatch, raises=AssertionError("child must not be spawned"))

        with pytest.raises(ValueError, match="no previous command found"):
            pin_last_command(_build_app())
        assert load_pin() is None

    def test_legacy_stash_still_pins(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """A stash from an older state (no tokens recorded) still pins."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")
        _fake_run(monkeypatch, raises=AssertionError("child must not be spawned"))

        rows, source, replayed = pin_last_command(_build_csv_app())
        assert rows == 2
        assert source == "plexctl movies list"
        assert replayed is False


def _build_session_app(command_name: str) -> typer.Typer:
    """Minimal app exposing one named top-level command plus pin."""
    app = typer.Typer()

    @app.command(command_name)
    def _command() -> None:
        typer.echo(f"SESSION:{command_name}")

    register_pin(app)
    return app


class TestReprintIntegration:
    """End-to-end tests through a real Typer app and CliRunner."""

    def test_pinned_table_reprints_after_command(self, pin_env: Path) -> None:
        """The result callback reprints the pin after every command."""
        save_pin(["title", "year"], [{"title": "Pinned Row", "year": "1982"}], "pin source")

        result = CliRunner().invoke(_build_app(), ["hello"])
        assert result.exit_code == 0
        assert "HELLO_TOKEN" in result.output
        assert "Pinned Row" in result.output
        assert result.output.count("Pinned Row") == 1

    def test_pin_command_prints_pin_exactly_once(self, pin_env: Path) -> None:
        """The pin command confirms once; the callback owns the reprint."""
        stash_last_output(CSV_MOVIES, "plexctl movies list")

        result = CliRunner().invoke(_build_app(), ["pin"])
        assert result.exit_code == 0
        assert "Pinned 2 row(s) from 'plexctl movies list'" in result.output
        assert result.output.count("Fight Club") == 1

    def test_unpin_command_clears_pin(self, pin_env: Path) -> None:
        """unpin removes the table from subsequent command output."""
        save_pin(["title"], [{"title": "Pinned Row"}], "pin source")

        result = CliRunner().invoke(_build_app(), ["unpin"])
        assert result.exit_code == 0
        assert "Pin cleared" in result.output
        assert "Pinned Row" not in result.output
        assert load_pin() is None

    def test_pin_without_output_fails(self, pin_env: Path) -> None:
        """Pinning with no stashed CSV reports the failure and exits 1."""
        result = CliRunner().invoke(_build_app(), ["pin"])

        assert result.exit_code == 1
        assert "Cannot pin" in result.output


class TestReprintGuard:
    """The reprint callback skips the long-running ``repl`` session command.

    ``repl`` is a session, not a one-shot command, so re-running its
    completion (e.g. when the outer app returns after the session ends)
    must not emit a stray reprint.
    """

    def test_skips_repl_command(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """The ``repl`` session command does not trigger a reprint."""
        capture_csv(CSV_MOVIES, "plexctl movies list")
        buffer = _capture_console(monkeypatch)

        result = CliRunner().invoke(_build_session_app("repl"), ["repl"])
        assert result.exit_code == 0
        assert "SESSION:repl" in result.output
        assert "Fight Club" not in buffer.getvalue()

    def test_reprints_non_repl_command(self, pin_env: Path, monkeypatch: MonkeyPatch) -> None:
        """Any non-``repl`` command reprints the pinned table once."""
        capture_csv(CSV_MOVIES, "plexctl movies list")
        buffer = _capture_console(monkeypatch)

        result = CliRunner().invoke(_build_session_app("server"), ["server"])
        assert result.exit_code == 0
        assert "SESSION:server" in result.output
        assert buffer.getvalue().count("Fight Club") == 1


class TestCommandSource:
    """Labelling of the running command used to title pinned tables."""

    def test_falls_back_to_argv_without_context(self, monkeypatch: MonkeyPatch) -> None:
        """Outside a Click context the label is derived from ``sys.argv``."""
        monkeypatch.setattr("sys.argv", ["plexctl", "server", "info", "--json"])
        assert command_source() == "server info --json"

    def test_default_without_argv(self, monkeypatch: MonkeyPatch) -> None:
        """A bare invocation falls back to a stable placeholder."""
        monkeypatch.setattr("sys.argv", ["plexctl"])
        assert command_source() == "previous command"
