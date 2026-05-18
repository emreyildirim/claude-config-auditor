"""Token counting — isolated to its own module because the underlying
tokenizer is the most likely thing to change in future phases.

What we know (as of writing):
- Anthropic publishes an official `count_tokens` REST endpoint, but Phase 1
  is strictly offline (see brief section 3, 4).
- Anthropic does not publish the Claude 3+ tokenizer vocabulary, so any
  fully-offline count is an approximation. We say so loudly in the report.

What we do:
1. If `tiktoken` is installed, use `cl100k_base` (OpenAI's GPT-4 tokenizer).
   Empirically this lands within ~10-15% of Anthropic's count for English
   prose and Markdown — close enough for "is my CLAUDE.md too big?".
2. Otherwise, fall back to a character-based heuristic (~3.7 chars/token
   for English/Markdown). This is rougher but always available.

Either way, the `Estimator` reports which method it used so the report
can be honest about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Method = Literal["tiktoken-cl100k_base", "char-heuristic"]


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
    """Return the best available estimator, with a human note explaining it."""
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        return Estimator(
            method="char-heuristic",
            note=(
                "Estimated using a character heuristic (~3.7 chars/token). "
                "Install the `tokenizer` extra (pip install 'claude-config-auditor[tokenizer]') "
                "for a closer estimate via tiktoken."
            ),
        )
    return Estimator(
        method="tiktoken-cl100k_base",
        note=(
            "Estimated using tiktoken `cl100k_base` (OpenAI GPT-4 tokenizer). "
            "Anthropic does not publish the Claude tokenizer; this is a "
            "close-but-not-exact proxy. Treat numbers as ±10-15%."
        ),
    )


def _tiktoken_count(text: str) -> int:
    global _TIKTOKEN_ENCODER
    if _TIKTOKEN_ENCODER is None:
        import tiktoken

        _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_TIKTOKEN_ENCODER.encode(text, disallowed_special=()))


def _heuristic_count(text: str) -> int:
    # ~3.7 chars/token for English+Markdown is a common rule of thumb.
    # We use len() over characters (not bytes) to keep multi-byte chars
    # from inflating the count.
    return max(1, round(len(text) / 3.7))
