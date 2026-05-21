"""Tests for framework_shape.detect and the audit findings that read it."""

from __future__ import annotations

from pathlib import Path

from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.checks import health as health_check
from claude_config_auditor.checks import skills as skills_check
from claude_config_auditor.framework_shape import detect
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator


# --- helpers ----------------------------------------------------------------

def _agent(dir: Path, slug: str, *, desc: str = "Reasonable description that "
           "is long enough to pass the very-short check.") -> None:
    (dir / f"{slug}.md").write_text(
        f"---\nname: {slug}\ndescription: {desc}\n---\nbody\n", encoding="utf-8"
    )


def _skill(root: Path, slug: str, *, desc: str = "Reasonable skill description "
           "that is long enough to pass the very-short check.") -> None:
    sd = root / slug
    sd.mkdir(parents=True)
    (sd / "SKILL.md").write_text(
        f"---\nname: {slug}\ndescription: {desc}\n---\nbody\n", encoding="utf-8"
    )


# --- detect() ---------------------------------------------------------------

def test_detect_bmad_marker(tmp_path: Path):
    (tmp_path / "_bmad").mkdir()
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    _skill(tmp_path / ".claude" / "skills", "one")
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name == "BMAD"
    assert shape.intentional_no_claude_md is True
    assert any("_bmad/" in m for m in shape.markers)


def test_detect_claude_flow_marker(tmp_path: Path):
    (tmp_path / ".claude-flow").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name == "claude-flow"
    # claude-flow writes CLAUDE.md by default — not intentional to skip.
    assert shape.intentional_no_claude_md is False


def test_detect_skill_pack_heuristic(tmp_path: Path):
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    for i in range(12):
        _skill(skills_dir, f"skill-{i}")
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name == "skill-pack"
    assert shape.intentional_no_claude_md is True


def test_detect_agent_pack_heuristic(tmp_path: Path):
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    for i in range(31):
        _agent(agents_dir, f"a-{i}")
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name == "agent-pack"
    assert shape.intentional_no_claude_md is True


def test_detect_command_pack(tmp_path: Path):
    cmd_dir = tmp_path / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    for i in range(6):
        (cmd_dir / f"c-{i}.md").write_text(
            f"---\nname: c-{i}\ndescription: a slash command.\n---\nbody\n",
            encoding="utf-8",
        )
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name == "command-pack"
    assert shape.intentional_no_claude_md is True


def test_detect_returns_unknown_for_plain_project(tmp_path: Path):
    """A normal project with CLAUDE.md + a couple of agents is NOT a
    framework install — we should not misclassify it."""
    (tmp_path / "CLAUDE.md").write_text("# normal\n", encoding="utf-8")
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    _agent(agents_dir, "one")
    _agent(agents_dir, "two")
    sc = scan(tmp_path)

    shape = detect(tmp_path, sc)
    assert shape.name is None
    assert shape.intentional_no_claude_md is False


# --- HLT005 hint enrichment + HLT007 emission -------------------------------

def test_bmad_target_enriches_hlt005_hint_and_emits_hlt007(tmp_path: Path):
    """For a BMAD-shaped target, HLT005 still fires (CLAUDE.md is in fact
    missing) — but the hint must point at the BMAD convention so the
    user sees that it may be intentional. Separately, HLT007 fires as
    positive context."""
    (tmp_path / "_bmad").mkdir()
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    for i in range(12):
        _skill(skills_dir, f"s-{i}")
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)
    shape = detect(tmp_path, sc)

    findings = health_check.audit(sc, budget, 5000, budget.tokens_by_path, shape)
    codes = [f.code for f in findings]

    assert "HLT005" in codes, "HLT005 must still fire — finding is not suppressed"
    hlt005 = next(f for f in findings if f.code == "HLT005")
    assert "BMAD" in (hlt005.hint or "")

    assert "HLT007" in codes
    hlt007 = next(f for f in findings if f.code == "HLT007")
    assert "BMAD" in hlt007.message


def test_plain_project_hlt005_uses_generic_hint(tmp_path: Path):
    """When no framework shape matches, HLT005's hint should be the
    generic guidance, not a framework-specific sentence."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    for i in range(6):
        _agent(agents_dir, f"a-{i}")
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)
    shape = detect(tmp_path, sc)

    # An agent-pack heuristic might fire here if we crossed 30 agents,
    # but with 6 agents it should not. Confirm:
    assert shape.name in (None, "agent-pack")

    findings = health_check.audit(sc, budget, 5000, budget.tokens_by_path, shape)
    hlt005 = next((f for f in findings if f.code == "HLT005"), None)
    assert hlt005 is not None
    hint = (hlt005.hint or "")
    if shape.intentional_no_claude_md and shape.name:
        # If we did fall into a heuristic, hint must name it.
        assert shape.name in hint
    else:
        # Generic hint must NOT mention BMAD or skill-pack etc.
        for framework_name in ("BMAD", "claude-flow", "skill-pack",
                               "agent-pack", "command-pack"):
            assert framework_name not in hint


# --- AGT007 is about eager footprint, not body --------------------------

def test_agt007_does_not_fire_on_heavy_body(tmp_path: Path):
    """An agent with a short description and a huge body should NOT
    trip AGT007 — the body is on-demand, it does not bloat session start."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    big_body = "# Heading\n\n" + ("This is body content. " * 600) + "\n"
    (agents_dir / "rich.md").write_text(
        "---\nname: rich\ndescription: A normal-length, routing-friendly "
        "description for a deep-dive agent.\n---\n" + big_body,
        encoding="utf-8",
    )
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)

    findings = agents_check.audit(
        sc.agents,
        budget.tokens_by_path,
        budget.eager_tokens_by_path,
    ).findings

    codes = [f.code for f in findings]
    assert "AGT007" not in codes, (
        "AGT007 must not fire on heavy body — body is on-demand. "
        f"Got: {codes}"
    )


def test_agt007_fires_when_frontmatter_is_heavy(tmp_path: Path):
    """An agent that stuffs reference documentation into the description
    DOES bloat session start. AGT007 must catch it."""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    huge_desc = "This is a sentence that documents usage. " * 80   # ~1700 chars
    (agents_dir / "bloated.md").write_text(
        f"---\nname: bloated\ndescription: {huge_desc}\n---\nshort body\n",
        encoding="utf-8",
    )
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)

    findings = agents_check.audit(
        sc.agents,
        budget.tokens_by_path,
        budget.eager_tokens_by_path,
    ).findings

    codes = [f.code for f in findings]
    assert "AGT007" in codes


# --- SKL005 is about eager footprint, not body --------------------------

def test_skl005_does_not_fire_on_heavy_body(tmp_path: Path):
    """Same as AGT007: skill body is on-demand. A large SKILL.md body
    should not trigger SKL005 on its own."""
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    sd = skills_dir / "deep"
    sd.mkdir()
    big_body = "# Section\n\n" + ("Lots of usage text. " * 800) + "\n"
    (sd / "SKILL.md").write_text(
        "---\nname: deep\ndescription: A skill with a small description "
        "and a long body of usage docs.\n---\n" + big_body,
        encoding="utf-8",
    )
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)

    findings = skills_check.audit(
        sc.skills,
        budget.tokens_by_path,
        budget.eager_tokens_by_path,
    ).findings

    codes = [f.code for f in findings]
    assert "SKL005" not in codes


# --- commands/ scanning + budget integration ----------------------------

def test_commands_directory_is_scanned(tmp_path: Path):
    cmd_dir = tmp_path / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "deploy.md").write_text(
        "---\nname: deploy\ndescription: Deploy to staging.\n---\nbody\n",
        encoding="utf-8",
    )
    (cmd_dir / "test.md").write_text(
        "---\nname: test\ndescription: Run the test suite.\n---\nbody\n",
        encoding="utf-8",
    )
    sc = scan(tmp_path)
    assert len(sc.commands) == 2


def test_commands_are_fully_on_demand_in_budget(tmp_path: Path):
    """Slash commands must contribute 0 to eager_load_total — they only
    load when the user types `/<name>`."""
    cmd_dir = tmp_path / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    body = "# Title\n\n" + ("Command body content. " * 50) + "\n"
    (cmd_dir / "deploy.md").write_text(
        "---\nname: deploy\ndescription: Deploy to staging.\n---\n" + body,
        encoding="utf-8",
    )
    sc = scan(tmp_path)
    est = get_estimator()
    budget = budget_check.compute(sc, est)

    cmd_cat = next(c for c in budget.categories if c.name == "command")
    assert cmd_cat.file_count == 1
    assert cmd_cat.eager_tokens == 0
    assert cmd_cat.lazy_tokens > 0
    # Eager total is not inflated by commands.
    assert budget.eager_load_total == 0
