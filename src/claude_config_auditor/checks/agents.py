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
# AGT007 flags eager footprint, not total file size. An agent's body
# is on-demand (runs in its own sub-session), so a 6 000-token body is
# fine. The cost paid on every session is the YAML frontmatter — name,
# description, allowed-tools. A frontmatter above ~250 tokens usually
# means usage docs leaked into the description; that's a real bug.
AGENT_EAGER_BLOAT_TOKENS = 250
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


def audit(
    agents: list[FileRecord],
    tokens_by_path: dict[str, int],
    eager_tokens_by_path: dict[str, int] | None = None,
) -> AgentReport:
    """Lint agent definitions.

    `tokens_by_path` maps `FileRecord.relpath` to total token cost
    (eager + lazy). `eager_tokens_by_path` is the per-file frontmatter
    cost — the slice loaded into the session at startup. AGT007 reads
    this map; if not provided, AGT007 is skipped (defensive: keeps the
    function callable from older code paths until they are updated).
    """
    if eager_tokens_by_path is None:
        eager_tokens_by_path = {}
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

        eager_cost = eager_tokens_by_path.get(rec.relpath, 0)
        if eager_cost > AGENT_EAGER_BLOAT_TOKENS:
            findings.append(
                Finding(
                    severity="info",
                    code="AGT007",
                    message=(
                        f"agent's session-start cost is ~{eager_cost} tokens "
                        "(YAML frontmatter loaded on every session)"
                    ),
                    file=rec.relpath,
                    hint=(
                        "The body of an agent is on-demand (it loads only "
                        "when this agent runs in its own sub-session). The "
                        "frontmatter is paid every session. If reference "
                        "material has leaked into the `description`, move "
                        "it into the body."
                    ),
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
                "Word-overlap heuristic (not semantic) — the signal is "
                "coarse and may include false positives where descriptions "
                "share boilerplate. If this is a real conflict, make each "
                "description's trigger condition disjoint. Accurate "
                "semantic detection is planned as opt-in (Phase 3, "
                "`pip install claude-config-auditor[semantic]`)."
            )
            findings.append(
                Finding(
                    severity="info",
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
                    severity="info",
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
