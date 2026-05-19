"""End-to-end checks on the good and broken fixtures."""

from pathlib import Path

from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.checks import health as health_check
from claude_config_auditor.checks import skills as skills_check
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator

FIXTURES = Path(__file__).parent / "fixtures"


def test_good_fixture_has_no_errors():
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    tbp = budget.tokens_by_path

    findings = []
    findings.extend(agents_check.audit(result.agents, tbp).findings)
    findings.extend(skills_check.audit(result.skills, tbp).findings)
    findings.extend(health_check.audit(result, budget, 5000, tbp))

    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"unexpected errors in good fixture: {errors}"


def test_broken_fixture_surfaces_expected_errors():
    result = scan(FIXTURES / "broken")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    tbp = budget.tokens_by_path

    findings = []
    findings.extend(agents_check.audit(result.agents, tbp).findings)
    findings.extend(skills_check.audit(result.skills, tbp).findings)
    findings.extend(health_check.audit(result, budget, 5000, tbp))

    codes = {f.code for f in findings}
    assert "AGT001" in codes  # bad yaml
    assert "AGT003" in codes  # missing description (no-description.md)
    assert "AGT008" in codes  # description overlap
    assert "SKL001" in codes or "SKL002" in codes  # broken skill


def test_budget_headline_is_nonzero_on_good_fixture():
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    assert budget.session_start_total > 0
    assert 0.0 <= budget.percent_of_window < 100.0


def test_budget_files_sorted_largest_first():
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    token_counts = [f.tokens for f in budget.files]
    assert token_counts == sorted(token_counts, reverse=True)


def test_empty_dir_produces_zero_budget():
    result = scan(FIXTURES / "empty")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    assert budget.session_start_total == 0
    findings = health_check.audit(result, budget, 5000, budget.tokens_by_path)
    codes = {f.code for f in findings}
    assert "HLT006" in codes


def test_agent_overlap_is_bidirectional():
    """Both sides of an overlapping description pair should be flagged.

    The broken fixture has `overlap-a.md` and `overlap-b.md`, hand-crafted
    to score well above the Jaccard threshold. A finding must be emitted
    against each — not just one of them.
    """
    result = scan(FIXTURES / "broken")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    findings = agents_check.audit(result.agents, budget.tokens_by_path).findings

    overlap = [f for f in findings if f.code == "AGT008"]
    flagged_files = {f.file or "" for f in overlap}
    assert any("overlap-a" in p for p in flagged_files), flagged_files
    assert any("overlap-b" in p for p in flagged_files), flagged_files

    # Symmetric pair → exactly 2 AGT008 findings, not 1 and not 4.
    assert len(overlap) == 2, overlap


def test_eager_load_excludes_agent_and_skill_bodies():
    """The headline metric must only count what Claude actually pulls
    into the session at startup: full CLAUDE.md/rules plus agent/skill
    frontmatter. Bodies of agents and skills are on-demand and must
    not appear in eager_load_total."""
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)

    # CLAUDE.md and rules are fully eager.
    for f in budget.files:
        if f.category in ("claude.md", "rule"):
            assert f.eager_tokens == f.tokens, f
            assert f.lazy_tokens == 0, f

    # Agents and skills (with valid frontmatter) split into eager + lazy
    # such that they sum to the total. Whether eager or lazy dominates
    # depends on how the user wrote the file — not a contract.
    agent_files = [f for f in budget.files if f.category == "agent"]
    assert agent_files, "fixture should have at least one agent"
    for f in agent_files:
        assert f.eager_tokens > 0, f  # frontmatter exists
        assert f.lazy_tokens > 0, f   # body exists
        assert f.eager_tokens + f.lazy_tokens == f.tokens, f


def test_eager_load_is_smaller_than_total_config():
    """For any project with non-trivial agents/skills, eager < total."""
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    assert budget.eager_load_total < budget.total_config_tokens
    assert budget.eager_load_total + budget.on_demand_total == budget.total_config_tokens


def test_session_start_total_alias_returns_eager():
    """Backward-compat: the old session_start_total accessor now points
    at eager_load_total. Documented in the budget docstring."""
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    assert budget.session_start_total == budget.eager_load_total


def test_tokens_by_path_matches_files():
    """BudgetReport.tokens_by_path should be the single source of truth."""
    result = scan(FIXTURES / "good")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    tbp = budget.tokens_by_path
    # Same set of paths
    assert set(tbp.keys()) == {f.relpath for f in budget.files}
    # Same token counts
    for f in budget.files:
        assert tbp[f.relpath] == f.tokens
