# Case studies

Five real `claude-audit` reports against popular Claude Code frameworks,
each one freshly set up on a clean macOS machine and audited with the
default tokenizer (`tiktoken` `cl100k_base`) and the opt-in `--semantic`
flag enabled. Open any file in a browser — they are self-contained, no
network required.

The HTML is the unmodified output of `claude-audit --html`, except that
the local filesystem path shown in the report header was scrubbed (the
files lived under `~/Documents/projects/claude-test/...` on the test
machine; the report header now shows `~/projects/<framework>` so only
the framework name is visible).

| Framework | Always loaded | Window | Files | Findings | Report |
|---|---:|---:|---:|---:|---|
| BMAD | 2,304 tok | 1.2% | 45 | 0 | [bmad-audit.html](bmad-audit.html) |
| Claude-Code-Game-Studios | 17,267 tok | 8.6% | 138 | 0 | [claude-code-game-studios-audit.html](claude-code-game-studios-audit.html) |
| claude-flow (now ruflo) | 3,631 tok | 1.8% | 194 | 4 warn | [claude-flow-audit.html](claude-flow-audit.html) |
| SuperClaude | 3,725 tok | 1.9% | 52 | 0 | [superclaude-audit.html](superclaude-audit.html) |
| wshobson (4 plugins) | 2,378 tok | 1.2% | 41 | 0 | [wshobson-audit.html](wshobson-audit.html) |

## How each install was produced

- **BMAD** — `npx bmad-method install --yes --tools claude-code` on a
  clean directory, then a hand-written `CLAUDE.md` + `docs/PRD.md`
  (Mock SaaS analytics dashboard) added on top to mirror a realistic
  in-progress BMAD project rather than an empty fresh install.
- **Claude-Code-Game-Studios** — `git clone Donchitos/Claude-Code-Game-Studios`.
  The repo ships `CLAUDE.md` and `.claude/` directly; there is no
  separate installer.
- **claude-flow** — `npx claude-flow@alpha init --force --no-global`. The
  npm package `claude-flow@alpha` now resolves to **ruflo** (the
  framework was renamed); the report reflects ruflo's current install
  shape.
- **SuperClaude** — official installer (`superclaude install`) run with
  `HOME` redirected to a sandbox directory so the test machine's real
  `~/.claude/` was not touched; the resulting agents, slash commands and
  `CLAUDE.md` were consolidated into one folder before auditing.
- **wshobson** — `git clone wshobson/agents` (a Claude Code plugin
  marketplace, ~80 plugins). Four representative plugins were
  materialized into `.claude/` to mimic the "user installed these
  plugins" shape: `backend-development`, `frontend-mobile-development`,
  `cicd-automation`, `code-refactoring`.

## What to look at

- **Always loaded** is the eager session-start cost: full CLAUDE.md +
  rules + only the YAML frontmatter of every agent and skill. This is
  the figure that competes for the main window.
- **Window** is that same number expressed as a percentage of a 200k
  reference context window. Anything under ~10% is comfortable; the
  reports above sit between 1.2% and 8.6%, which is roughly what a
  well-built framework should look like.
- **Files** counts everything the auditor scanned (CLAUDE.md + agents
  + skills + rules + slash commands).
- **Findings** is the number of `AGTxxx` / `SKLxxx` / `HLTxxx` issues
  flagged. Four of five frameworks audit cleanly (zero findings) under
  the current threshold tuning; claude-flow / ruflo carries four
  warnings, which is the heaviest of the set.

## What these reports validate

Reviewers of the auditor have asked two reasonable questions:

> *"You claim `~5-10%` tokenizer accuracy and pick certain thresholds
> for `AGT007` / `SKL005` etc. — show your work."*

The metric tuning notes in [CHANGELOG.md](../CHANGELOG.md) reference
these installs. The reports here are the artifacts. They exist so a
future contributor can re-run `claude-audit` on the same frameworks
and compare against a known baseline.

> *"Does this actually surface real problems on real projects?"*

Yes — claude-flow / ruflo carries four warnings under the current
threshold tuning, and the Claude-Code-Game-Studios report flags an
**8.6% window occupation** even though nothing is broken (that's
17,267 tokens of always-loaded weight on every session before the
user types anything). The other three frameworks audit clean, which
is also a signal: a tidy install produces a quiet report and a heavy
one tells you exactly where to thin down.
