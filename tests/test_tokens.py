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
    # ~3.7 chars/token: a 370-char string should be ~100 tokens.
    est = Estimator(method="char-heuristic", note="test")
    text = "x" * 370
    n = est.count(text)
    assert 80 <= n <= 120


def test_get_estimator_returns_a_valid_method():
    est = get_estimator()
    assert est.method in ("tiktoken-cl100k_base", "char-heuristic")
    assert est.note  # has a human-readable note
