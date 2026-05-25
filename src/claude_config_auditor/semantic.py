"""Opt-in semantic overlap detection for AGT008.

By default the auditor stays fully offline; the `[semantic]` extras
package adds a one-off ~80MB local model download. Once installed,
`--semantic` activates this module: the same candidate pairs the
Jaccard pass identifies are re-evaluated against cosine similarity
over MiniLM sentence embeddings. Pairs the embedding model confirms
become a higher severity; pairs it disagrees with disappear from the
report. No network call is made at audit time after the one-off
model download.

Threshold rationale: 0.82 is the empirical cutoff observed on
sentence-transformers `all-MiniLM-L6-v2` between "trivially
paraphrased" (~0.9) and "thematically related but distinct" (~0.7)
short descriptions. It is conservative on purpose — false positives
in this layer would defeat the whole point of upgrading the
heuristic.

This module imports `sentence_transformers` lazily so the rest of the
auditor keeps running without the extras package installed.
"""

from __future__ import annotations

from typing import Any

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_COSINE_THRESHOLD = 0.82

_MODEL: Any = None
_AVAILABLE: bool | None = None


def available() -> bool:
    """Return True iff the `[semantic]` extras package is importable.

    The check is cached after the first call so we don't keep
    re-importing on every invocation.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        import sentence_transformers  # noqa: F401
        _AVAILABLE = True
    except ImportError:
        _AVAILABLE = False
    return _AVAILABLE


def _get_model() -> Any:
    """Load the embedding model on first use. The download (~80MB) only
    happens the first time; subsequent calls reuse the local cache
    that `sentence_transformers` maintains under
    `~/.cache/huggingface/`."""
    global _MODEL
    if _MODEL is None:
        if not available():
            raise RuntimeError(
                "--semantic requires the [semantic] extras package. "
                "Install with: pip install 'claude-config-auditor[semantic]' "
                "(or remove --semantic to use the default word-overlap "
                "heuristic)."
            )
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(_MODEL_NAME)
    return _MODEL


def encode_descriptions(texts: list[str]) -> Any:
    """Embed a batch of descriptions in a single call (more efficient
    than encoding pairs one at a time). Returns a 2D array shaped
    `(len(texts), embedding_dim)` ready for pairwise cosine."""
    model = _get_model()
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def cosine(vec_a: Any, vec_b: Any) -> float:
    """Cosine similarity in (-1, 1). Works on numpy vectors. We avoid
    a hard numpy dependency at module import time by accepting whatever
    `encode_descriptions` returned."""
    import numpy as np

    a = np.asarray(vec_a, dtype=float)
    b = np.asarray(vec_b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
