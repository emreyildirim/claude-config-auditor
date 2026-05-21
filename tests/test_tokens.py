"""Token estimator behaves sanely whether tiktoken is installed or not."""

from claude_config_auditor.tokens import Estimator, get_estimator


def test_estimator_returns_zero_for_empty_string():
    est = get_estimator()
    assert est.count("") == 0


def test_heuristic_estimator_is_monotonic():
    est = Estimator(method="char-heuristic", note="test")
    short = est.count("hello")
    long = est.count("hello " * 200)
    assert long > short


def test_heuristic_estimator_is_in_a_sensible_range():
    # ~4.5 chars/token (tuned for Markdown/YAML): 450 chars → ~100 tokens.
    est = Estimator(method="char-heuristic", note="test")
    text = "x" * 450
    n = est.count(text)
    assert 80 <= n <= 120


def test_get_estimator_returns_a_valid_method():
    est = get_estimator()
    assert est.method in ("tiktoken-cl100k_base", "char-heuristic")
    assert est.note  # has a human-readable note


def test_default_estimator_prefers_tiktoken_when_available():
    """tiktoken is a hard dependency from v0.1.x onward; the default
    estimator must use it when no env override is set."""
    est = get_estimator()
    assert est.method == "tiktoken-cl100k_base"


def test_env_var_forces_heuristic_fallback(monkeypatch):
    """Setting CLAUDE_AUDIT_TOKENIZER=heuristic must bypass tiktoken even
    when tiktoken is importable — useful for benchmarking the fallback."""
    monkeypatch.setenv("CLAUDE_AUDIT_TOKENIZER", "heuristic")
    est = get_estimator()
    assert est.method == "char-heuristic"
    assert "heuristic" in est.note.lower()
