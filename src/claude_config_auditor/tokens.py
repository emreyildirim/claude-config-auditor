"""Token counting — isolated to its own module because the underlying
tokenizer is the most likely thing to change in future phases.

What we know (as of writing):
- Anthropic publishes an official `count_tokens` REST endpoint. By
  default the auditor stays strictly offline; the `--accurate` flag is
  the explicit, opt-in opt-out and never changes default behaviour.
- Anthropic does not publish the Claude 3+/4 tokenizer vocabulary, so
  any fully-offline count is an approximation. We say so loudly in
  the report.

What we do:
1. `tiktoken` (`cl100k_base`, OpenAI's GPT-4 tokenizer) is a hard
   dependency as of v0.1.x. Empirically it lands within ~5-10% of
   Anthropic's count for the Markdown/YAML content we actually scan
   — close enough for "is my CLAUDE.md too big?", and meaningfully
   more accurate than a character heuristic in real config files
   (the heuristic systematically over-counts by ~10-30% on Markdown).
2. If tiktoken fails to import for any reason (a stripped-down CI
   image, a no-network install, a platform without precompiled
   wheels), we fall back to a character-based estimator that uses
   ~4.5 chars/token — the median observed across BMAD, claude-flow,
   wshobson, VoltAgent, and SuperClaude config files. The classic
   "3.7 chars/token" rule of thumb is for English prose; Markdown
   with headings, lists, and YAML frontmatter sits noticeably higher.
3. If the user passes `--accurate`, counts route through Anthropic's
   public `count_tokens` endpoint. Requires `ANTHROPIC_API_KEY` in
   the environment; raises `RuntimeError` otherwise (the flag is an
   explicit opt-in and we refuse to silently fall back). Each unique
   `(sha256(text), model)` is counted once and cached on disk under
   `~/.cache/claude-config-auditor/` so repeated audits of the same
   files don't re-hit the API.

Either way, the `Estimator` reports which method it used so the report
can be honest about it.

Forcing the fallback: set the env var ``CLAUDE_AUDIT_TOKENIZER=heuristic``
to bypass tiktoken even when it is installed (useful for benchmarking,
or for comparing reports across machines where tiktoken may not be
available).

Overriding the accurate cache location (mostly for tests): set
``CLAUDE_AUDIT_ACCURATE_CACHE_DIR`` to a directory of your choice.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Method = Literal[
    "tiktoken-cl100k_base",
    "char-heuristic",
    "anthropic-accurate",
]

# Median chars-per-token observed across the May 2026 cross-framework
# comparison (BMAD, claude-flow, wshobson, VoltAgent, SuperClaude).
# Markdown/YAML config sits at ~4.5; the old 3.7 figure was for
# English prose and over-counted by ~10-30% on real config files.
_CHARS_PER_TOKEN_HEURISTIC = 4.5

_DEFAULT_ACCURATE_MODEL = "claude-sonnet-4-5"
_ANTHROPIC_COUNT_TOKENS_URL = "https://api.anthropic.com/v1/messages/count_tokens"
_ANTHROPIC_VERSION = "2023-06-01"
_ACCURATE_CACHE_FILENAME = "accurate-tokens-v1.json"


@dataclass(frozen=True)
class Estimator:
    method: Method
    note: str
    model: str | None = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.method == "tiktoken-cl100k_base":
            return _tiktoken_count(text)
        if self.method == "anthropic-accurate":
            assert self.model is not None
            return _anthropic_count(text, self.model)
        return _heuristic_count(text)


_TIKTOKEN_ENCODER = None
_ACCURATE_CACHE: dict[str, dict[str, int]] | None = None
_ACCURATE_CACHE_DIRTY = False
_ACCURATE_ATEXIT_REGISTERED = False


def get_estimator(
    *,
    accurate: bool = False,
    accurate_model: str | None = None,
) -> Estimator:
    """Return the best available estimator, with a human note explaining it.

    Order of preference (default, offline):
      1. `tiktoken` with `cl100k_base` (default — installed as a hard
         dependency).
      2. Character heuristic, when tiktoken cannot be imported OR when
         the user sets ``CLAUDE_AUDIT_TOKENIZER=heuristic`` in the env
         to force the fallback (handy for benchmarking).

    Opt-in (online):
      * `accurate=True` routes counts through Anthropic's
        `count_tokens` endpoint. Requires `ANTHROPIC_API_KEY` in the
        env; raises RuntimeError otherwise. Per-text results are
        cached across runs.
    """
    if accurate:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "--accurate requires ANTHROPIC_API_KEY in the environment. "
                "Set ANTHROPIC_API_KEY=sk-ant-... or omit --accurate to use "
                "the default tiktoken estimator."
            )
        model = accurate_model or _DEFAULT_ACCURATE_MODEL
        _register_accurate_atexit()
        return Estimator(
            method="anthropic-accurate",
            model=model,
            note=(
                f"Counts routed through Anthropic's count_tokens endpoint "
                f"(model: {model}). Each unique input is counted once and "
                f"cached under {_accurate_cache_dir()}; repeat audits do "
                "not re-hit the API. The Anthropic endpoint counts the "
                "tokens of a user-message containing the text, so expect "
                "~3-5 tokens of message framing overhead per file."
            ),
        )

    forced = (os.environ.get("CLAUDE_AUDIT_TOKENIZER") or "").strip().lower()
    if forced == "heuristic":
        return Estimator(
            method="char-heuristic",
            note=(
                f"Estimated using a character heuristic "
                f"(~{_CHARS_PER_TOKEN_HEURISTIC} chars/token, tuned for "
                "Markdown/YAML config). Forced via CLAUDE_AUDIT_TOKENIZER=heuristic."
            ),
        )

    try:
        import tiktoken  # noqa: F401
    except ImportError:
        return Estimator(
            method="char-heuristic",
            note=(
                f"Estimated using a character heuristic "
                f"(~{_CHARS_PER_TOKEN_HEURISTIC} chars/token, tuned for "
                "Markdown/YAML config). Install tiktoken for a closer estimate: "
                "pip install tiktoken."
            ),
        )
    return Estimator(
        method="tiktoken-cl100k_base",
        note=(
            "Estimated using tiktoken `cl100k_base` (OpenAI GPT-4 tokenizer). "
            "Anthropic does not publish the Claude tokenizer; this is a "
            "close-but-not-exact proxy. Treat numbers as ±5-10% on Markdown/YAML. "
            "Pass --accurate (and set ANTHROPIC_API_KEY) for ground-truth counts."
        ),
    )


def _tiktoken_count(text: str) -> int:
    global _TIKTOKEN_ENCODER
    if _TIKTOKEN_ENCODER is None:
        import tiktoken

        _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_TIKTOKEN_ENCODER.encode(text, disallowed_special=()))


def _heuristic_count(text: str) -> int:
    # See the module docstring for why 4.5 (not the classic 3.7). We
    # use len() over characters (not bytes) to keep multi-byte chars
    # from inflating the count.
    return max(1, round(len(text) / _CHARS_PER_TOKEN_HEURISTIC))


# ---- Anthropic count_tokens (opt-in --accurate) -----------------------


def _accurate_cache_dir() -> Path:
    custom = os.environ.get("CLAUDE_AUDIT_ACCURATE_CACHE_DIR")
    if custom:
        return Path(custom)
    return Path.home() / ".cache" / "claude-config-auditor"


def _accurate_cache_path() -> Path:
    return _accurate_cache_dir() / _ACCURATE_CACHE_FILENAME


def _load_accurate_cache() -> dict[str, dict[str, int]]:
    global _ACCURATE_CACHE
    if _ACCURATE_CACHE is not None:
        return _ACCURATE_CACHE
    path = _accurate_cache_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _ACCURATE_CACHE = data
            else:
                _ACCURATE_CACHE = {}
        except (OSError, json.JSONDecodeError):
            _ACCURATE_CACHE = {}
    else:
        _ACCURATE_CACHE = {}
    return _ACCURATE_CACHE


def _save_accurate_cache() -> None:
    global _ACCURATE_CACHE_DIRTY
    if not _ACCURATE_CACHE_DIRTY or _ACCURATE_CACHE is None:
        return
    path = _accurate_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(_ACCURATE_CACHE, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)
    _ACCURATE_CACHE_DIRTY = False


def _register_accurate_atexit() -> None:
    global _ACCURATE_ATEXIT_REGISTERED
    if _ACCURATE_ATEXIT_REGISTERED:
        return
    atexit.register(_save_accurate_cache)
    _ACCURATE_ATEXIT_REGISTERED = True


def _anthropic_count(text: str, model: str) -> int:
    cache = _load_accurate_cache()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    bucket = cache.get(sha)
    if bucket is not None and model in bucket:
        return bucket[model]
    count = _anthropic_count_uncached(text, model)
    cache.setdefault(sha, {})[model] = count
    global _ACCURATE_CACHE_DIRTY
    _ACCURATE_CACHE_DIRTY = True
    return count


def _anthropic_count_uncached(text: str, model: str) -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY missing at the moment of the count_tokens call. "
            "It was set earlier but unset before this request."
        )
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": text}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _ANTHROPIC_COUNT_TOKENS_URL,
        data=payload,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                return int(body["input_tokens"])
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, ValueError) as e:
            last_err = e
            if attempt == 1:
                continue
    raise RuntimeError(
        f"--accurate: count_tokens request failed after retry: {last_err}"
    )
