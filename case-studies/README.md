# Case studies

Six real `claude-audit` reports against popular Claude Code frameworks,
each one freshly installed on a clean macOS machine in May 2026 and
audited with the default tokenizer (`tiktoken` `cl100k_base`). Open any
file in a browser — they are self-contained, no network required.

The HTML is the unmodified output of `claude-audit --html`, except that
the local filesystem path shown in the report header was scrubbed (the
files lived under `~/Documents/projects/...` on the test machine; that
prefix was removed so only the framework name remains).

| Framework | Always loaded | Window | Files | Findings | Report |
|---|---:|---:|---:|---:|---|
| BMAD | 3,066 tok | 1.5% | 70 | 2 | [bmad-audit.html](bmad-audit.html) |
| Claude-Code-Game-Studios | 17,858 tok | 8.9% | 138 | 3 | [claude-code-game-studios-audit.html](claude-code-game-studios-audit.html) |
| claude-flow | 7,474 tok | 3.7% | 217 | 33 | [claude-flow-audit.html](claude-flow-audit.html) |
| SuperClaude | 591 tok | 0.3% | 51 | 3 | [superclaude-audit.html](superclaude-audit.html) |
| VoltAgent | 10,010 tok | 5.0% | 145 | 1 | [voltagent-audit.html](voltagent-audit.html) |
| wshobson | 1,275 tok | 0.6% | 29 | 1 | [wshobson-audit.html](wshobson-audit.html) |

## What to look at

- **Always loaded** is the eager session-start cost: full CLAUDE.md +
  rules + only the YAML frontmatter of every agent and skill. This is
  the figure that competes for the main window.
- **Window** is that same number expressed as a percentage of a 200k
  reference context window. Anything under ~10% is comfortable; the
  reports above sit between 0.3% and 8.9%, which is roughly what a
  well-built framework should look like.
- **Files** counts everything the auditor scanned (CLAUDE.md + agents
  + skills + rules + slash commands).
- **Findings** is the number of `AGTxxx` / `SKLxxx` / `HLTxxx` issues
  flagged. The wide spread (1 → 33) is informative on its own — most
  frameworks are clean, claude-flow leans on the auditor most.

## What these reports validate

Reviewers of the auditor have asked two reasonable questions:

> *"You claim `~5-10%` tokenizer accuracy and pick certain thresholds
> for `AGT007` / `SKL005` etc. — show your work."*

The metric tuning notes in [CHANGELOG.md](../CHANGELOG.md) reference
exactly these six installs. The reports here are the artifacts. They
exist so a future contributor can re-run `claude-audit` on the same
six frameworks and compare against a known baseline.

> *"Does this actually surface real problems on real projects?"*

Yes — the `claude-flow` report carries 33 findings, the
`Claude-Code-Game-Studios` report flags an `8.9%` window occupation
with three agent-description issues, and the smaller frameworks audit
clean. The check-set isn't noisy on tidy installs and isn't silent on
messy ones.
