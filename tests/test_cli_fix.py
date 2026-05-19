"""Tests for the Phase 2 `fix` and `revert` CLI subcommands.

These exercise the wiring layer in cli.py specifically:

  - the default-subcommand prepend trick that keeps `claude-audit .`
    routing to audit (covered alongside the existing test_cli tests),
  - the fix subcommand with --dry-run, --apply-all, no-TTY refusal,
    and the no-proposals short-circuit,
  - the revert subcommand: --list, latest, specific session, missing
    session, drift error, --force.

The proposers themselves and the apply/revert primitives are covered
by their own focused test modules.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from claude_config_auditor.cli import main


# --- Helpers ----------------------------------------------------------------

def _broken_project(tmp_path: Path) -> Path:
    """A project guaranteed to have fix-able findings (AGT004 short
    description, AGT008 overlap) so the fix path has something to do."""
    target = tmp_path / "p"
    agents_dir = target / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (target / "CLAUDE.md").write_text("# Project\n\n## Rules\n\n- Foo.\n")
    (agents_dir / "short.md").write_text(
        "---\nname: short\ndescription: tiny\n---\nbody\n"
    )
    return target


def _clean_project(tmp_path: Path) -> Path:
    """A project with no fix-able findings — fix should short-circuit."""
    target = tmp_path / "p"
    target.mkdir(parents=True)
    (target / "CLAUDE.md").write_text(
        "# Project\n\n## Rules\n\n- Use type hints.\n- Test before pushing.\n"
    )
    return target


# --- Backward compat: audit is still the default subcommand --------------

def test_no_subcommand_routes_to_audit(tmp_path: Path, capsys):
    """`claude-audit .` (no subcommand) must still run an audit, not
    error out from the argparse subparser."""
    target = _clean_project(tmp_path)
    rc = main([str(target), "--no-color"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Always-loaded session footprint" in out


def test_explicit_audit_subcommand_works(tmp_path: Path, capsys):
    target = _clean_project(tmp_path)
    rc = main(["audit", str(target), "--no-color"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Always-loaded session footprint" in out


def test_no_args_audits_cwd(tmp_path: Path, capsys, monkeypatch):
    target = _clean_project(tmp_path)
    monkeypatch.chdir(target)
    rc = main([])
    assert rc == 0
    capsys.readouterr()  # drain


# --- fix: short-circuit and dry-run --------------------------------------

def test_fix_with_no_proposals_exits_cleanly(tmp_path: Path, capsys):
    target = _clean_project(tmp_path)
    rc = main(["fix", str(target), "--no-color", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No fix proposals" in out


def test_fix_dry_run_shows_diff_does_not_apply(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    agent = target / ".claude" / "agents" / "short.md"
    before = agent.read_text()

    rc = main(["fix", str(target), "--no-color", "--dry-run"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "dry-run" in out.lower()
    assert agent.read_text() == before     # untouched
    assert not (target / ".claude-config-auditor").exists()


# --- fix: --apply-all batches yes ----------------------------------------

def test_fix_apply_all_modifies_files_with_no_prompt(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    agent = target / ".claude" / "agents" / "short.md"
    before = agent.read_text()

    rc = main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()

    assert rc == 0
    after = agent.read_text()
    assert after != before
    assert "TODO (claude-audit," in after


# --- fix: non-TTY refusal ------------------------------------------------

def test_fix_non_tty_without_consent_flag_errors(tmp_path: Path, capsys,
                                                  monkeypatch):
    """If stdin isn't a real terminal and neither --dry-run nor
    --apply-all is given, fix must refuse — it can't ask for consent."""
    target = _broken_project(tmp_path)

    class FakeStdin(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr("sys.stdin", FakeStdin(""))
    rc = main(["fix", str(target), "--no-color"])
    err = capsys.readouterr().err

    assert rc == 2
    assert "interactive terminal" in err
    # File must be untouched.
    agent = target / ".claude" / "agents" / "short.md"
    assert "TODO (claude-audit," not in agent.read_text()


# --- fix: target validation ----------------------------------------------

def test_fix_missing_target_errors(capsys, tmp_path: Path):
    rc = main(["fix", str(tmp_path / "nope"), "--dry-run"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "does not exist" in err


# --- revert: list --------------------------------------------------------

def test_revert_list_shows_no_sessions_when_empty(tmp_path: Path, capsys):
    target = _clean_project(tmp_path)
    rc = main(["revert", str(target), "--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No backup sessions" in out


def test_revert_list_enumerates_sessions(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()

    rc = main(["revert", str(target), "--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "backup session" in out
    # The session-id format is "YYYY-MM-DDThh-mm-ssZ-<6hex>".
    assert "Z-" in out


# --- revert: latest ------------------------------------------------------

def test_revert_latest_restores_files(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    agent = target / ".claude" / "agents" / "short.md"
    before = agent.read_text()

    main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()
    assert "TODO (claude-audit," in agent.read_text()  # confirm modified

    rc = main(["revert", str(target)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Reverted" in out
    assert agent.read_text() == before


# --- revert: missing session --------------------------------------------

def test_revert_unknown_session_errors(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()

    rc = main(["revert", str(target), "no-such-session"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_revert_with_no_sessions_at_all_errors(tmp_path: Path, capsys):
    target = _clean_project(tmp_path)
    rc = main(["revert", str(target)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "No backup sessions" in err


# --- revert: drift detection + --force -----------------------------------

def test_revert_refuses_when_files_drift(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    agent = target / ".claude" / "agents" / "short.md"

    main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()

    # User then edits the fix's output by hand.
    agent.write_text(agent.read_text() + "\n# extra hand edit\n")

    rc = main(["revert", str(target)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "drift" in err.lower()
    # File must NOT have been overwritten.
    assert "# extra hand edit" in agent.read_text()


def test_revert_force_overrides_drift(tmp_path: Path, capsys):
    target = _broken_project(tmp_path)
    agent = target / ".claude" / "agents" / "short.md"
    pristine = agent.read_text()

    main(["fix", str(target), "--no-color", "--apply-all"])
    capsys.readouterr()
    agent.write_text("totally different content")

    rc = main(["revert", str(target), "--force"])
    capsys.readouterr()
    assert rc == 0
    assert agent.read_text() == pristine
