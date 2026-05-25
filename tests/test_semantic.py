"""Opt-in semantic overlap detection (AGT008).

The real embedding pipeline is exercised by the smoke-test reported
in the PR description; the tests below mock encode/cosine so unit
tests do not download the ~80MB model on every CI run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_config_auditor.checks import agents as agents_check
from claude_config_auditor.checks import budget as budget_check
from claude_config_auditor.scanner import scan
from claude_config_auditor.tokens import get_estimator
from claude_config_auditor import semantic as semantic_mod

FIXTURES = Path(__file__).parent / "fixtures"


def _broken_agents():
    """Reuse the broken fixture — it ships overlap-a/overlap-b which
    are designed to score above the Jaccard threshold."""
    result = scan(FIXTURES / "broken")
    est = get_estimator()
    budget = budget_check.compute(result, est)
    return result.agents, budget.tokens_by_path, budget.eager_tokens_by_path


def test_default_keeps_agt008_at_info_severity():
    agents, tbp, ebp = _broken_agents()
    findings = agents_check.audit(agents, tbp, ebp).findings
    agt008 = [f for f in findings if f.code == "AGT008"]
    assert agt008, "broken fixture should still flag the overlap pair"
    assert all(f.severity == "info" for f in agt008)
    # Old hint vocabulary must not leak in alongside the new wording.
    assert all("Word-overlap heuristic" in f.hint for f in agt008)


def test_semantic_drops_pairs_below_cosine_threshold(monkeypatch):
    """Jaccard finds the pair, semantic disagrees → finding is dropped."""
    agents, tbp, ebp = _broken_agents()
    # Cosine well below 0.82 — emulates "shared boilerplate, different scope".
    monkeypatch.setattr(
        semantic_mod, "encode_descriptions", lambda texts: [[1.0]] * len(texts)
    )
    monkeypatch.setattr(semantic_mod, "cosine", lambda a, b: 0.50)
    findings = agents_check.audit(agents, tbp, ebp, semantic=True).findings
    agt008 = [f for f in findings if f.code == "AGT008"]
    assert agt008 == [], f"semantic should have dropped these: {agt008}"


def test_semantic_upgrades_pairs_above_cosine_threshold(monkeypatch):
    """Jaccard + semantic confirm → finding is upgraded to warning."""
    agents, tbp, ebp = _broken_agents()
    monkeypatch.setattr(
        semantic_mod, "encode_descriptions", lambda texts: [[1.0]] * len(texts)
    )
    monkeypatch.setattr(semantic_mod, "cosine", lambda a, b: 0.95)
    findings = agents_check.audit(agents, tbp, ebp, semantic=True).findings
    agt008 = [f for f in findings if f.code == "AGT008"]
    assert agt008, "semantic-confirmed overlap should still be reported"
    assert all(f.severity == "warning" for f in agt008)
    # New message must carry both signals so the user sees what was
    # measured, not just a generic verdict.
    assert all("word-overlap" in f.message for f in agt008)
    assert all("semantic cos" in f.message for f in agt008)


def test_cosine_at_exactly_threshold_is_kept(monkeypatch):
    """Boundary: equal to threshold counts as a confirmed match."""
    agents, tbp, ebp = _broken_agents()
    monkeypatch.setattr(
        semantic_mod, "encode_descriptions", lambda texts: [[1.0]] * len(texts)
    )
    monkeypatch.setattr(
        semantic_mod, "cosine",
        lambda a, b: semantic_mod.SEMANTIC_COSINE_THRESHOLD,
    )
    findings = agents_check.audit(agents, tbp, ebp, semantic=True).findings
    assert [f for f in findings if f.code == "AGT008"]


def test_cosine_helper_math():
    """The cosine helper is plain math; verify the two endpoints."""
    v_same = [1.0, 0.0, 0.0]
    v_orth = [0.0, 1.0, 0.0]
    v_opp = [-1.0, 0.0, 0.0]
    assert semantic_mod.cosine(v_same, v_same) == pytest.approx(1.0)
    assert semantic_mod.cosine(v_same, v_orth) == pytest.approx(0.0)
    assert semantic_mod.cosine(v_same, v_opp) == pytest.approx(-1.0)
    # Zero vector falls back to 0.0 instead of raising.
    assert semantic_mod.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_available_reflects_extras_install_state():
    """`available()` must return a bool that matches whether the
    `sentence_transformers` package can actually be imported in this
    environment. CI runs without the `[semantic]` extras; local dev
    typically runs with them. Both states are valid — what we're
    asserting here is that the detection is honest, not that the
    extras are present."""
    try:
        import sentence_transformers  # noqa: F401
        expected = True
    except ImportError:
        expected = False
    # Reset the cached probe so a previous test can't poison this one.
    semantic_mod._AVAILABLE = None
    assert semantic_mod.available() is expected


def test_get_model_raises_when_extras_missing(monkeypatch):
    """If sentence_transformers cannot be imported, the loader must
    raise a RuntimeError that names the install hint."""
    # Force the cache to "not available" and block the import.
    monkeypatch.setattr(semantic_mod, "_AVAILABLE", False)
    monkeypatch.setattr(semantic_mod, "_MODEL", None)
    with pytest.raises(RuntimeError, match=r"\[semantic\] extras package"):
        semantic_mod._get_model()
