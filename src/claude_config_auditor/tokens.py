"""Token counting — isolated to its own module because the underlying
tokenizer is the most likely thing to change in future phases.

What we know (as of writing):
- Anthropic publishes an official `count_tokens` REST endpoint, but the
  auditor is strictly offline by design (brief sections 3-4): no API
  calls, no auth, runs in CI and on plane-mode laptops alike.
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

Either way, the `Estimator` reports which method it used so the report
can be honest about it.

Forcing the fallback: set the env var ``CLAUDE_AUDIT_TOKENIZER=heuristic``
to bypass tiktoken even when it is installed (useful for benchmarking,
or for comparing reports across machines where tiktoken may not be
available).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Method = Literal["tiktoken-cl100k_base", "char-heuristic"]

# Median chars-per-token observed across the May 2026 cross-framework
# comparison (BMAD, claude-flow, wshobson, VoltAgent, SuperClaude).
# Markdown/YAML config sits at ~4.5; the old 3.7 figure was for
# English prose and over-counted by ~10-30% on real config files.
_CHARS_PER_TOKEN_HEURISTIC = 4.5


@dataclass(frozen=True)
class Estimator:
    method: Method
    note: str

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self.method == "tiktoken-cl100k_base":
            return _tiktoken_count(text)
        return _heuristic_count(text)


_TIKTOKEN_ENCODER = None


def get_estimator() -> Estimator:
    """Return the best available estimator, with a human note explaining it.

    Order of preference:
      1. `tiktoken` with `cl100k_base` (default — installed as a hard
         dependency).
      2. Character heuristic, when tiktoken cannot be imported OR when
         the user sets ``CLAUDE_AUDIT_TOKENIZER=heuristic`` in the env
         to force the fallback (handy for benchmarking).
    """
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
            "close-but-not-exact proxy. Treat numbers as ±5-10% on Markdown/YAML."
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
