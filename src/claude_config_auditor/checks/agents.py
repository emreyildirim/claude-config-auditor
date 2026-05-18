"""Agent quality audit — see brief section 5.2.

Checks per agent file:
- frontmatter valid + required `name` and `description` present
- `description` not empty / too short / too long
- token bloat
- description overlap between agents (Claude routes by description text;
  near-duplicates cause the wrong agent to fire).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from claude_config_auditor.findings import Finding
from claude_config_auditor.scanner import FileRecord


# Thresholds. Tuned to be opinionated but not noisy.
DESCRIPTION_MIN_CHARS = 30
DESCRIPTION_SHORT_CHARS = 60        # below this -> warning, "Claude may not trigger"
DESCRIPTION_LONG_CHARS = 600        # above this -> warning, "wasting tokens on a description"
AGENT_TOKEN_BLOAT = 2_000           # above this for a single agent -> info
OVERLAP_JACCARD_THRESHOLD = 0.55    # word-overlap; deliberately not semantic
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "for", "on",
    "with", "at", "by", "from", "is", "are", "be", "this", "that", "it",
    "as", "use", "used", "when", "if", "you", "your", "agent", "claude",
    "task", "tasks", "should", "must", "can",
}


@dataclass
class AgentReport:
    findings: list[Finding]


def audit(agents: list[FileRecord], tokens_by_path: dict[str, int]) -> AgentReport:
    """Lint agent definitions.

    `tokens_by_path` maps `FileRecord.relpath` to the pre-computed token cost
    of the file (built once by the caller from BudgetReport). The check
    reuses it rather than invoking the tokenizer again.
    """
    findings: list[Finding] = []

    # Per-agent checks.
    for rec in agents:
        if not rec.frontmatter_ok:
            findings.append(
                Finding(
                    severity="error",
                    code="AGT001",
                    message=f"frontmatter could not be parsed ({rec.parse_warning})",
                    file=rec.relpath,
                    hint="Fix the YAML between the '---' lines at the top of the file.",
                )
            )
            continue

        name = (rec.frontmatter.get("name") or "").strip()
        description = (rec.frontmatter.get("description") or "").strip()

        if not name:
            findings.append(
                Finding(
                    severity="error",
                    code="AGT002",
                    message="missing required field `name` in frontmatter",
                    file=rec.relpath,
                )
            )

        if not description:
            findings.append(
                Finding(
                    severity="error",
                    code="AGT003",
                    message="missing required field `description` in frontmatter",
                    file=rec.relpath,
                    hint="Claude routes to agents by description text. An empty description means this agent will never fire.",
                )
            )
        else:
            dlen = len(description)
            if dlen < DESCRIPTION_MIN_CHARS:
                findings.append(
                    Finding(
                        severity="warning",
                        code="AGT004",
                        message=f"`description` is very short ({dlen} chars)",
                        file=rec.relpath,
                        hint="Short descriptions make routing unreliable. Add concrete trigger examples.",
                    )
                )
            elif dlen < DESCRIPTION_SHORT_CHARS:
                findings.append(
                    Finding(
                        severity="info",
                        code="AGT005",
                        message=f"`description` is short ({dlen} chars) — consider adding example triggers",
                        file=rec.relpath,
                    )
                )
            elif dlen > DESCRIPTION_LONG_CHARS:
                findings.append(
                    Finding(
                        severity="warning",
                        code="AGT006",
                        message=f"`description` is unusually long ({dlen} chars)",
                        file=rec.relpath,
                        hint="Every agent description is loaded on every session. Trim to the routing signal.",
                    )
                )

        token_cost = tokens_by_path.get(rec.relpath, 0)
        if token_cost > AGENT_TOKEN_BLOAT:
            findings.append(
                Finding(
                    severity="info",
                    code="AGT007",
                    message=f"agent file is large (~{token_cost} tokens)",
                    file=rec.relpath,
                    hint="Large agents inflate every session. Move reference material into a skill or external doc.",
                )
            )

    # Cross-agent overlap.
    sigs: list[tuple[FileRecord, str, set[str]]] = []
    for rec in agents:
        if not rec.frontmatter_ok:
            continue
        desc = (rec.frontmatter.get("description") or "").strip()
        if not desc:
            continue
        words = _content_words(desc)
        if len(words) >= 4:  # too short to compare meaningfully
            sigs.append((rec, desc, words))

    # Jaccard is a symmetric measure (J(A,B) == J(B,A)) so the overlap
    # itself applies to *both* agents in a colliding pair. We emit a
    # finding against each side so neither file appears clean when the
    # user filters or scans by path.
    for i in range(len(sigs)):
        rec_a, _, words_a = sigs[i]
        for j in range(i + 1, len(sigs)):
            rec_b, _, words_b = sigs[j]
            j_score = _jaccard(words_a, words_b)
            if j_score < OVERLAP_JACCARD_THRESHOLD:
                continue
            hint = (
                "Overlapping descriptions cause Claude to pick the wrong "
                "agent. Make each description's trigger condition disjoint."
            )
            findings.append(
                Finding(
                    severity="warning",
                    code="AGT008",
                    message=(
                        f"description overlaps with `{rec_b.relpath}` "
                        f"(word-overlap {j_score:.0%})"
                    ),
                    file=rec_a.relpath,
                    hint=hint,
                )
            )
            findings.append(
                Finding(
                    severity="warning",
                    code="AGT008",
                    message=(
                        f"description overlaps with `{rec_a.relpath}` "
                        f"(word-overlap {j_score:.0%})"
                    ),
                    file=rec_b.relpath,
                    hint=hint,
                )
            )

    return AgentReport(findings=findings)


def _content_words(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zçğıöşüÇĞİÖŞÜ]{3,}", text.lower())
    return {t for t in tokens if t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0
