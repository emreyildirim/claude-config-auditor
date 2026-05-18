"""Unit tests for the overlap-detection helpers in checks.agents.

Integration coverage lives in test_checks.py
(test_agent_overlap_is_bidirectional). The tests below pin the
underlying math so threshold tuning is intentional, not accidental.
"""

import pytest

from claude_config_auditor.checks.agents import (
    OVERLAP_JACCARD_THRESHOLD,
    _content_words,
    _jaccard,
)


# --- _jaccard: pure math ----------------------------------------------------

def test_jaccard_identical_sets_score_one():
    s = {"alpha", "beta", "gamma"}
    assert _jaccard(s, s) == 1.0


def test_jaccard_disjoint_sets_score_zero():
    assert _jaccard({"alpha", "beta"}, {"gamma", "delta"}) == 0.0


def test_jaccard_empty_inputs_score_zero():
    assert _jaccard(set(), set()) == 0.0
    assert _jaccard({"alpha"}, set()) == 0.0
    assert _jaccard(set(), {"alpha"}) == 0.0


def test_jaccard_half_overlap():
    a = {"x", "y", "z"}
    b = {"x", "w"}
    # intersection = {x} → 1
    # union = {x, y, z, w} → 4
    assert _jaccard(a, b) == pytest.approx(0.25)


def test_jaccard_is_symmetric():
    a = {"foo", "bar", "baz", "qux"}
    b = {"foo", "bar", "zap"}
    assert _jaccard(a, b) == _jaccard(b, a)


# --- _content_words: tokenization and stopword stripping --------------------

def test_content_words_strips_short_tokens_and_stopwords():
    # "a", "is" are stopwords/too short; everything ≥ 3 chars stays.
    words = _content_words("Use this agent when a task is reviewing code")
    # "use", "agent", "when", "task", "this", "is" are stopwords;
    # "a" is < 3 chars. "reviewing", "code" should remain.
    assert "reviewing" in words
    assert "code" in words
    assert "use" not in words
    assert "agent" not in words


def test_content_words_lowercases():
    words = _content_words("Reviews Pull Requests")
    assert words == {"reviews", "pull", "requests"}


def test_content_words_handles_turkish_characters():
    words = _content_words("Çıkar şıralı içerik üretir")
    # Each Turkish word ≥ 3 chars and not in the English stopword list.
    assert "çıkar" in words
    assert "şıralı" in words
    assert "içerik" in words
    assert "üretir" in words


def test_content_words_ignores_punctuation_and_numbers():
    words = _content_words("Use the v2.3 endpoint, fast!")
    assert "endpoint" in words
    assert "fast" in words
    assert "v2" not in words      # has a digit, regex requires letters
    assert "the" not in words     # stopword


# --- Threshold contract -----------------------------------------------------

def test_threshold_is_a_sensible_value():
    """Catch accidental threshold changes. 0.55 was chosen deliberately:
    too low (e.g. 0.3) over-flags unrelated agents that share generic
    words; too high (e.g. 0.8) misses paraphrased duplicates."""
    assert 0.4 < OVERLAP_JACCARD_THRESHOLD < 0.75


def test_paraphrased_duplicates_exceed_threshold():
    """The two fixture descriptions in tests/fixtures/broken — different
    wording, same intent — should clear the threshold."""
    a = _content_words(
        "Reviews pull requests for code quality, naming, and obvious "
        "bugs in the diff. Use after a diff lands or when the user says "
        '"review this PR".'
    )
    b = _content_words(
        "Reviews pull requests for code quality and naming and obvious "
        "bugs in a diff. Use after a diff lands when the user requests "
        "a PR review."
    )
    assert _jaccard(a, b) >= OVERLAP_JACCARD_THRESHOLD


def test_genuinely_distinct_descriptions_stay_below_threshold():
    """Code reviewer vs security reviewer in tests/fixtures/good —
    related topics but legitimately distinct triggers — should NOT
    cross the threshold."""
    a = _content_words(
        "Reviews pull requests for code quality, naming, and obvious "
        'bugs. Use after a diff lands or when the user says "review '
        'this PR" or "look at these changes". Not for security review.'
    )
    b = _content_words(
        "Audits a diff for security issues — injection, auth bypass, "
        "secret exposure, unsafe deserialization, and OWASP top-10 "
        'patterns. Use when the user asks for a "security review" or '
        "when the change touches auth, crypto, or input parsing."
    )
    assert _jaccard(a, b) < OVERLAP_JACCARD_THRESHOLD
