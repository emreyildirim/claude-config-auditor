"""Opt-in `--accurate` flag routes counts through Anthropic's
count_tokens endpoint. Tests mock urllib so no real network call is
ever made.
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch
from urllib import error as urllib_error

import pytest

from claude_config_auditor import tokens


@pytest.fixture(autouse=True)
def _isolate_module_state(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory cache and a tmp on-disk cache
    location, so writes never leak into the developer's real
    ~/.cache/."""
    monkeypatch.setenv("CLAUDE_AUDIT_ACCURATE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(tokens, "_ACCURATE_CACHE", None)
    monkeypatch.setattr(tokens, "_ACCURATE_CACHE_DIRTY", False)
    monkeypatch.setattr(tokens, "_ACCURATE_ATEXIT_REGISTERED", True)  # skip atexit
    yield


def _fake_response(input_tokens: int):
    body = json.dumps({"input_tokens": input_tokens}).encode("utf-8")

    class _Ctx:
        def __enter__(self_inner):
            class _R:
                @staticmethod
                def read():
                    return body

            return _R()

        def __exit__(self_inner, *exc):
            return False

    return _Ctx()


def test_accurate_without_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        tokens.get_estimator(accurate=True)


def test_accurate_with_api_key_returns_correct_method(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    assert est.method == "anthropic-accurate"
    assert est.model == "claude-sonnet-4-5"
    assert "count_tokens" in est.note


def test_accurate_respects_custom_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True, accurate_model="claude-haiku-4-5")
    assert est.model == "claude-haiku-4-5"
    assert "claude-haiku-4-5" in est.note


def test_count_hits_endpoint_and_returns_input_tokens(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(tokens.urllib.request, "urlopen", return_value=_fake_response(42)) as m:
        assert est.count("hello world") == 42
    assert m.call_count == 1
    sent = m.call_args.args[0]
    payload = json.loads(sent.data)
    assert payload["model"] == "claude-sonnet-4-5"
    assert payload["messages"][0]["content"] == "hello world"
    assert sent.headers["X-api-key"] == "sk-ant-test"


def test_repeated_count_for_same_text_is_cached(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(tokens.urllib.request, "urlopen", return_value=_fake_response(7)) as m:
        est.count("repeat me")
        est.count("repeat me")
        est.count("repeat me")
    assert m.call_count == 1


def test_different_models_get_separate_cache_entries(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est_sonnet = tokens.get_estimator(accurate=True, accurate_model="claude-sonnet-4-5")
    est_haiku = tokens.get_estimator(accurate=True, accurate_model="claude-haiku-4-5")
    with patch.object(tokens.urllib.request, "urlopen", side_effect=[
        _fake_response(10),
        _fake_response(11),
    ]) as m:
        assert est_sonnet.count("same text") == 10
        assert est_haiku.count("same text") == 11
    assert m.call_count == 2


def test_cache_persists_across_estimator_instances(monkeypatch):
    """A second get_estimator() call in the same process should reuse
    the in-memory cache; writing the cache to disk is exercised by the
    save/load round-trip test below."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est1 = tokens.get_estimator(accurate=True)
    with patch.object(tokens.urllib.request, "urlopen", return_value=_fake_response(5)):
        est1.count("hello")
    est2 = tokens.get_estimator(accurate=True)
    # No new urlopen mock — must come from cache, otherwise the test
    # fails with AttributeError because urlopen would do a real call.
    with patch.object(tokens.urllib.request, "urlopen", side_effect=AssertionError("cache miss")):
        assert est2.count("hello") == 5


def test_cache_round_trips_to_disk(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(tokens.urllib.request, "urlopen", return_value=_fake_response(13)):
        est.count("persist me")
    tokens._save_accurate_cache()
    # Wipe in-memory state and reload from disk.
    monkeypatch.setattr(tokens, "_ACCURATE_CACHE", None)
    monkeypatch.setattr(tokens, "_ACCURATE_CACHE_DIRTY", False)
    cache = tokens._load_accurate_cache()
    assert any(13 in bucket.values() for bucket in cache.values())


def test_retries_once_on_network_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    transient = urllib_error.URLError("transient")
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=[transient, _fake_response(99)],
    ) as m:
        assert est.count("flaky") == 99
    assert m.call_count == 2


def test_raises_after_retry_exhausted(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=urllib_error.URLError("permanent"),
    ):
        with pytest.raises(RuntimeError, match="failed after retry"):
            est.count("doomed")


def test_default_path_still_returns_tiktoken_or_heuristic(monkeypatch):
    """The accurate path is opt-in; calling get_estimator() with no
    args must not require ANTHROPIC_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    est = tokens.get_estimator()
    assert est.method in {"tiktoken-cl100k_base", "char-heuristic"}


def _http_error(code: int, body: bytes):
    return urllib_error.HTTPError(
        url=tokens._ANTHROPIC_COUNT_TOKENS_URL,
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,
        fp=BytesIO(body),
    )


def test_http_401_does_not_retry_and_surfaces_anthropic_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bad")
    est = tokens.get_estimator(accurate=True)
    body = json.dumps(
        {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    ).encode("utf-8")
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=_http_error(401, body),
    ) as m:
        with pytest.raises(RuntimeError, match="authentication_error.*invalid x-api-key"):
            est.count("hello")
    # Single attempt — no retry on 4xx.
    assert m.call_count == 1


def test_http_400_invalid_model_does_not_retry(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True, accurate_model="not-a-real-model")
    body = json.dumps(
        {"type": "error", "error": {"type": "invalid_request_error", "message": "model: not-a-real-model"}}
    ).encode("utf-8")
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=_http_error(400, body),
    ) as m:
        with pytest.raises(RuntimeError, match="invalid_request_error.*not-a-real-model"):
            est.count("hello")
    assert m.call_count == 1


def test_http_503_retries_once(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=[_http_error(503, b""), _fake_response(21)],
    ) as m:
        assert est.count("flaky") == 21
    assert m.call_count == 2


def test_http_error_with_non_json_body_falls_back_to_reason(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    est = tokens.get_estimator(accurate=True)
    with patch.object(
        tokens.urllib.request,
        "urlopen",
        side_effect=_http_error(403, b"<html>nginx 403</html>"),
    ):
        with pytest.raises(RuntimeError, match="HTTP 403"):
            est.count("hello")
