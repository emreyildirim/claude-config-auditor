"""Tests for the agent-description fix proposer.

The module produces *suggestions only* — comment annotations and a
single placeholder field for missing descriptions. The agent's runtime
behaviour must be unchanged after a fix applies: YAML still parses,
the description (when present) is unmodified, routing is unaffected.

Coverage focuses on:
  - Each finding code produces (or correctly does not produce) a proposal.
  - The serialised after-content is still valid YAML frontmatter.
  - Comments use the standard `TODO (claude-audit, AGTxxx)` marker so
    users can grep for them.
  - Files with structural issues (AGT001/AGT002) are refused.
  - End-to-end through the fix flow: revertable.
"""

from __future__ import annotations

import io
from pathlib import Path

from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.findings import Finding
from claude_config_auditor.fixes import run_fix_flow
from claude_config_auditor.fixes.agent_description import (
    propose_description_fixes,
)
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator
from claude_config_auditor.backup import revert_session


# --- Helpers -------------------------------------------------------------

def _write_agent(target: Path, name: str, raw: str) -> Path:
    """Drop a single agent file under a target tree and return its Path."""
    agents = target / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    p = agents / f"{name}.md"
    p.write_text(raw, encoding="utf-8")
    return p


def _scan_and_audit(target: Path):
    """Run Phase 1 audit, return (agents, all_findings, tokens_by_path)."""
    result = scan(target)
    est = get_estimator()
    budget = budget_check.compute(result, est)
    findings = agents_check.audit(result.agents, budget.tokens_by_path).findings
    return result.agents, findings, budget.tokens_by_path


# --- Empty input ---------------------------------------------------------

def test_no_findings_produces_no_proposals():
    proposals = propose_description_fixes([], [])
    assert proposals == []


def test_findings_with_no_handleable_code_produces_no_proposals(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(
        target, "ok-agent",
        "---\nname: ok-agent\n"
        "description: A clear, specific description well above the 60-char "
        "threshold so no AGT004/AGT005 fires, with concrete example "
        "trigger phrases for routing.\n"
        "---\nbody\n",
    )
    agents, findings, _ = _scan_and_audit(target)
    # The good agent has no native findings. Synthesise an AGT007 (bloat),
    # which is a code we explicitly do not handle.
    findings.append(Finding(
        severity="info",
        code="AGT007",
        message="agent file is large",
        file=agents[0].relpath,
    ))
    proposals = propose_description_fixes(agents, findings)
    assert proposals == []


# --- AGT003: missing description ----------------------------------------

def test_agt003_inserts_a_placeholder_description(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(target, "needs-desc",
                 "---\nname: needs-desc\n---\n\nbody\n")

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)

    assert len(proposals) == 1
    p = proposals[0]
    assert "AGT003" in p.source_code
    assert "description: TODO (claude-audit, AGT003)" in p.after
    # Original `name:` and body are still there.
    assert "name: needs-desc" in p.after
    assert "body" in p.after


def test_agt003_placeholder_is_inside_frontmatter(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(target, "x", "---\nname: x\n---\n\nbody\n")
    agents, findings, _ = _scan_and_audit(target)
    p = propose_description_fixes(agents, findings)[0]

    fm = p.after.split("---", 2)[1]  # text between first two '---'
    assert "description: TODO" in fm


# --- AGT004 / AGT005: short description ---------------------------------

def test_agt004_inserts_todo_comment_above_description(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(target, "short",
                 "---\nname: short\ndescription: tiny\n---\nbody\n")

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)

    assert len(proposals) == 1
    p = proposals[0]
    assert "AGT004" in p.source_code
    # Comment lines must precede the description line, all prefixed by `#`.
    after_lines = p.after.splitlines()
    desc_idx = next(i for i, l in enumerate(after_lines)
                    if l.lstrip().startswith("description:"))
    assert desc_idx >= 2
    assert after_lines[desc_idx - 1].lstrip().startswith("#")
    # Comment carries the standard marker so users can grep for it.
    assert any("TODO (claude-audit, AGT004)" in l for l in after_lines)


# --- AGT006: long description -------------------------------------------

def test_agt006_inserts_trim_hint(tmp_path: Path):
    target = tmp_path / "project"
    long_desc = "x" * 1200  # well over the 600-char threshold
    _write_agent(target, "huge",
                 f"---\nname: huge\ndescription: {long_desc}\n---\nbody\n")

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)

    assert len(proposals) == 1
    p = proposals[0]
    assert "AGT006" in p.source_code
    assert "TODO (claude-audit, AGT006)" in p.after
    # The original (unmodified) description line must still be present.
    assert long_desc in p.after


# --- AGT008: overlap (bidirectional) ------------------------------------

def test_agt008_annotates_both_overlapping_files(tmp_path: Path):
    target = tmp_path / "project"
    # Two agents whose descriptions overlap heavily — phrased differently
    # but built from the same vocabulary so the Jaccard threshold trips.
    _write_agent(target, "a", (
        "---\nname: a\n"
        "description: Reviews pull requests for code quality, naming, and "
        "obvious bugs in the diff. Use after a diff lands or when the "
        'user says "review this PR".\n'
        "---\n"
    ))
    _write_agent(target, "b", (
        "---\nname: b\n"
        "description: Reviews pull requests for code quality and naming "
        "and obvious bugs in a diff. Use after a diff lands when the "
        "user requests a PR review.\n"
        "---\n"
    ))

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)

    # Both agents should each get a proposal.
    paths = {p.path.name for p in proposals}
    assert paths == {"a.md", "b.md"}
    for p in proposals:
        assert "AGT008" in p.source_code
        assert "TODO (claude-audit, AGT008)" in p.after


# --- Skip rules ---------------------------------------------------------

def test_files_with_broken_yaml_are_skipped(tmp_path: Path):
    target = tmp_path / "project"
    # Hand-build broken frontmatter that will trip our parser.
    _write_agent(target, "bad", (
        "---\nname: bad\nthis line has no colon and breaks parsing\n"
        "description: malformed\n---\nbody\n"
    ))

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)
    assert proposals == []


def test_files_missing_name_are_skipped(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(target, "nameless", "---\ndescription: x\n---\nbody\n")

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)
    assert proposals == []


# --- Combined codes on the same file ------------------------------------

def test_multiple_codes_collapse_into_one_proposal(tmp_path: Path):
    target = tmp_path / "project"
    _write_agent(target, "tiny",
                 "---\nname: tiny\ndescription: hi\n---\nbody\n")
    # "hi" is 2 chars — should fire AGT004.
    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)
    # One proposal per file even if there were multiple findings.
    assert len(proposals) == 1


# --- End-to-end: applied + reverted -------------------------------------

def test_proposal_applies_and_reverts_through_fix_flow(tmp_path: Path):
    target = tmp_path / "project"
    agent_path = _write_agent(target, "short",
                              "---\nname: short\ndescription: tiny\n---\nbody\n")
    before_content = agent_path.read_text()

    agents, findings, _ = _scan_and_audit(target)
    proposals = propose_description_fixes(agents, findings)
    assert proposals  # sanity

    outcome = run_fix_flow(
        target, proposals,
        prompter=lambda p, r: "y",
        out=io.StringIO(),
        use_color=False,
    )

    # File was modified, TODO comment is present.
    assert outcome.applied
    after_content = agent_path.read_text()
    assert after_content != before_content
    assert "TODO (claude-audit, AGT004)" in after_content

    # Revert restores the original.
    revert_session(outcome.session_dir)
    assert agent_path.read_text() == before_content


# --- Output is still valid YAML frontmatter -----------------------------

def test_after_content_still_parses_as_yaml(tmp_path: Path):
    """Our string-level inserts must leave the YAML parseable. We
    re-scan the modified file and confirm the frontmatter still loads
    and still carries the original `name` and `description`."""
    target = tmp_path / "project"
    agent_path = _write_agent(target, "short",
                              "---\nname: short\ndescription: hi\n---\nbody\n")

    agents, findings, _ = _scan_and_audit(target)
    [p] = propose_description_fixes(agents, findings)
    agent_path.write_text(p.after)

    # Re-scan: should still parse cleanly.
    result2 = scan(target)
    [rec] = result2.agents
    assert rec.frontmatter_ok, rec.parse_warning
    assert rec.frontmatter.get("name") == "short"
    assert rec.frontmatter.get("description") == "hi"
