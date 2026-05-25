# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added — opt-in `--semantic` flag (Phase 3 shipped)

The `[semantic]` extras package (`pip install 'claude-config-auditor[semantic]'`)
pulls `sentence-transformers` for local embeddings; with the extras
installed, `claude-audit --semantic` re-evaluates every Jaccard
candidate pair against cosine similarity over MiniLM sentence
embeddings (`all-MiniLM-L6-v2`, ~80MB local model, no network at
audit time after the one-off download).

- Pairs whose cosine ≥ 0.82 are upgraded from the default `info`
  severity to `warning`; the message now carries both signals
  (`(word-overlap 67%, semantic cos 0.91)`) so the reader can see
  what was measured.
- Pairs whose cosine falls below 0.82 are dropped from the report
  entirely. This is the false-positive eliminator the word-overlap
  heuristic was missing — `unity-specialist.md` vs.
  `unreal-specialist.md` (high word-overlap, different game engines)
  no longer appears as a finding when `--semantic` is on.
- Smoke-tested against the live `you-are-president` project:
  default mode emitted 2 AGT008 info findings (Unity vs. Unreal
  specialist boilerplate); `--semantic` correctly dropped both.

Without the extras package, `--semantic` exits with code 2 and a
single-line stderr pointing at the install command. Default install
behaviour and the offline contract are unchanged.

### Changed — AGT008 severity dropped from `warning` to `info`

The word-overlap detection has known false positives (descriptions
sharing boilerplate but covering different scopes) and false
negatives (same-meaning descriptions phrased with different
vocabulary). Treating it as a warning overstated the confidence.
Severity is now `info`; the proper semantic detection ships behind
the `--semantic` opt-in described above.

### Changed — AGT008 hint names the heuristic and points at the opt-in

Previous wording read like a final verdict. New wording is honest
about the technique ("word-overlap heuristic, not semantic"),
acknowledges false positives, and points at the install path for
the semantic detection.

### Added — README cost snapshot moved above the fold

The six-framework headline table now sits right after "Why this
exists" instead of near the bottom. Readers opening the page see
real Always-loaded / Window / Files / Findings numbers in the first
screenful, which reinforces the cost-auditor positioning before the
feature list.

### Added — opt-in `--accurate` flag (Phase 2.5 shipped)

New `--accurate` flag on both `audit` and `fix` subcommands routes
token counts through Anthropic's public `count_tokens` endpoint
instead of the offline `tiktoken` estimator. Requires
`ANTHROPIC_API_KEY` in the environment — the flag is an explicit
opt-in from the offline contract and raises a clean error (exit code
2) if the key is missing rather than silently falling back. Each
unique `(sha256(text), model)` pair is counted once and cached under
`~/.cache/claude-config-auditor/accurate-tokens-v1.json`, so repeat
audits of the same project never re-hit the API. The retry strategy
is one extra attempt on transient network failures before surfacing
the error. Optional `--accurate-model` overrides the default model
(`claude-sonnet-4-5`). New `tests/test_accurate.py` mocks `urllib` so
no real network calls are made under test. Roadmap entry moves from
"in development" to "shipped".

### Added — README "Design principles" section, five-bullet contract

A new section between *"What it does not do"* and *"Install"* names
the contract the tool has held since day one: the `fix` mode either
annotates (via inert `# TODO` YAML markers) or moves content
mechanically — it never invents description text on the developer's
behalf. The section lists five reasons (predictability,
reversibility, no API key / network / per-run cost, no model-version
drift, human-in-the-loop) and frames them as the durable contract,
not a temporary state of the codebase.

### Changed — tagline sharpened to "non-destructive, annotate-don't-rewrite"

The header tagline now reads *"A **non-destructive** linter and cost
auditor for `.claude/` and `CLAUDE.md` — we annotate, we don't
rewrite."* The previous wording emphasised what the tool measured;
the new wording leads with what the tool refuses to do. Same product,
sharper positioning against LLM-autofix linters in the same niche.

### Removed — speculative Phase 3 ("Anthropic-API-assisted rewriting")

The roadmap no longer carries the Phase 3 line that hinted at future
LLM-assisted description rewriting. That direction would have
contradicted the "Design principles" contract; rather than leave a
speculative tension in the docs, the entry is dropped. Phase 2.5
(`--accurate` flag) is unchanged and stays in development.

### Added — pre-commit hook integration

`.pre-commit-hooks.yaml` now ships with the repo, so projects can wire
the auditor into the [pre-commit](https://pre-commit.com/) framework
with a single block in their `.pre-commit-config.yaml`. The hook runs
only when files under `.claude/` or `CLAUDE.md` change and uses the
existing `--fail-on` flag (`error` / `warning` / `never`) to decide
whether a commit is rejected. CI exit codes were already in place —
this entry just exposes them as a Git hook so blocking findings stop
shipping into `main` by accident.

### Changed — README spells out the two fix-mode philosophies

The "What `fix` can currently propose" section now explicitly names
the design split: `agent_description` *annotates* (the TODO marker is
a grep-friendly hint; the description text is left untouched on
purpose) while `claude_md_archive` *edits* (a section is physically
moved). External review feedback read the TODO comments as a half
measure; the addition clarifies that refusing to invent description
wording is a deliberate contract, with LLM-assisted rewriting reserved
for a possible Phase 3.

### Added — `case-studies/`: real audits against six popular frameworks

Six self-contained HTML reports under `case-studies/` produced by
running `claude-audit` against fresh installs of BMAD, claude-flow,
SuperClaude, VoltAgent, wshobson, and Claude-Code-Game-Studios in May
2026. Each report is the unmodified `--html` output (local filesystem
paths in the report header were scrubbed). The accompanying
`case-studies/README.md` summarises headline numbers (always-loaded
tokens, window occupation, file count, findings count) for every
framework. These are the same installs the metric-tuning notes
elsewhere in this changelog refer to — now visible as artifacts.

### Changed — softened the "Claude routes by description" claim

The "Why this exists" bullet that asserted *Claude routes by
description; near-duplicates cause silent misrouting* now reads *agents
are selected based on their description per Anthropic's docs; the
exact ranking algorithm isn't published, but overlapping descriptions
create routing ambiguity in practice*. The functional point is
unchanged; the wording is honest about what Anthropic publicly
documents.

### Added — Phase 2.5 roadmap entry: opt-in `--accurate` flag

Roadmap now flags a Phase 2.5 in development: an opt-in `--accurate`
flag that routes token counts through Anthropic's public
`count_tokens` endpoint (caller's API key, one request per scanned
file, locally cached). Default tokenizer stays `tiktoken`
`cl100k_base`; `--accurate` is a verification mode for reviewers who
want a ground-truth comparison against Anthropic's own counter.

### Added — Phase 2: opt-in `fix` mode
- New `fix` subcommand walks the user through fixable findings one by
  one. Each proposal shows a rationale, a unified diff (red removals,
  green additions), a per-file +/- summary, and an explicit prompt
  (y / n / a / q). Nothing is written without consent.
- New `revert` subcommand restores a previous backup session. With no
  arguments it reverts the most recent session; `--list` enumerates,
  and a session id targets a specific one. Drift detection compares
  each file's SHA-256 against the state recorded at fix time and
  refuses to overwrite hand-edited files unless `--force` is set.
- `--dry-run` previews every proposal without prompting or writing.
- `--apply-all` batches approval for non-interactive contexts (CI),
  still printing every diff before applying.
- Phase 2 proposers shipped:
  - **agent_description** annotates frontmatter with TODO YAML comments
    for AGT003 through AGT008. Comments are inert at Claude load time;
    behaviour is unchanged the moment the fix applies.
  - **claude_md_archive** moves stale CLAUDE.md sections into a
    sibling `CLAUDE.archive.md`. Heuristics are conservative: a four-
    step veto ladder skips protected headings (Rules, Conventions,
    Workflow, …), sections with operational language ("always",
    "must", "before using", …), and tiny sections below the
    150-token / 5-line minimum.
- Per-file atomic writes (temp + rename) and a single backup session
  around every accepted proposal set. Backups land at
  `<target>/.claude-config-auditor/backups/<id>/` with a plain-text
  manifest listing each file's SHA-256 before and after.
- `examples/sample-fix-output.md` walks through a dry-run and the
  surrounding interactive / revert flow.
- README gained a Phase 2 "Use" section and a safety-guarantees note;
  the roadmap is updated to mark Phase 2 as shipped.

### Changed — `tiktoken` is now a hard dependency (default tokenizer)

`tiktoken` (with the `cl100k_base` encoding) moved from
`[project.optional-dependencies]` into the base `dependencies` list.
The auditor's purpose is accurate token measurement; making the
better estimator the default keeps the headline numbers honest by
default. Empirically `cl100k_base` lands within ~5-10% of Anthropic's
count on the Markdown/YAML config the tool actually scans, versus
~10-30% over-counting for the character heuristic against the same
files (measured across BMAD, claude-flow, wshobson, VoltAgent, and
SuperClaude in May 2026).

Two safety nets remain:

- If `tiktoken` fails to import for any reason — a stripped-down CI
  image, a platform without precompiled wheels, a no-network install —
  the auditor transparently falls back to a character heuristic.
- The heuristic itself was retuned from the textbook `~3.7 chars/token`
  (which targets English prose) to `~4.5 chars/token` (the median
  observed across real Markdown/YAML config files). The classic 3.7
  figure was systematically over-counting our actual content.
- Setting `CLAUDE_AUDIT_TOKENIZER=heuristic` in the environment forces
  the fallback even when `tiktoken` is installed, for benchmarking or
  cross-machine comparison.

The report's "tokenizer" line still names whichever method ran, so
the source of the numbers stays visible to the reader.

### Added — sharper signals for third-party framework installs

- **Slash commands are now scanned and reported.** Files under
  `.claude/commands/` are picked up as a new `command` category in the
  budget report, terminal output, JSON, and the HTML dashboard (with
  its own colour). Commands have zero eager footprint — they only load
  when the user types `/<name>` — so the headline "Always loaded"
  metric is unaffected, but the count and on-demand weight are no
  longer invisible. Frameworks like SuperClaude (31 commands),
  claude-flow (88 commands), and wshobson plugins (7+ commands) were
  completely missing from the report before.
- **Framework-shape detection (`HLT007`).** The auditor now recognises
  well-known install patterns and surfaces them as a positive
  informational finding: a `_bmad/` marker dir → `BMAD-style`, a
  `.claude-flow/` dir → `claude-flow`, plus three heuristic shapes
  (`skill-pack`, `agent-pack`, `command-pack`) for unmarked frameworks
  whose layout is unambiguous. This is orientation, not a problem
  flag — but it makes the rest of the report much easier to read on a
  fresh BMAD or wshobson install.

### Changed — fixed the metric, not the message

The user-facing mentality stays the same: surface real signals, let
the user decide. These changes correct *what* AGT007, SKL005, and
HLT005 actually measure so the signals are honest, not quieter for
the sake of quiet.

- **AGT007 now flags eager footprint, not total file size.** An
  agent's body runs in its own sub-session — it does not bloat the
  main session. The old check fired on any agent over 2 000 tokens
  total, which caught legitimately rich subagent packs (VoltAgent,
  wshobson) and missed the actual failure mode: usage docs leaking
  into the YAML `description`. The new threshold is 250 tokens of
  *eager* footprint (frontmatter only). Across the five frameworks
  audited in May 2026, this removed 65+ noise findings without
  losing the one genuine eager-bloat case in claude-flow.
- **SKL005 follows the same logic.** A skill's body is read on use,
  not at session start. The check now fires only when SKILL.md
  frontmatter exceeds 250 eager tokens. Body bloat is still visible
  in the existing "Largest files" table — that's where it belongs.
- **HLT005 hint is framework-aware.** When a known framework shape is
  detected, HLT005 (no CLAUDE.md but agents/skills present) still
  fires — the file really is missing — but the hint now explains the
  framework's convention and lets the user decide whether to act.
  For unrecognised shapes, the generic hint is unchanged. Nothing is
  suppressed; the same fact is delivered with better context.

### Added
- README "FAQ" section answering the three most common questions
  visitors ask: does this work on non-Python projects (yes, any
  stack — the auditor only reads Markdown and YAML), will it modify
  files (no, Phase 1 is read-only and the test suite proves it), and
  why are token counts estimates (Anthropic does not publish the
  Claude 3+/4 tokenizer).
- README "Working with the JSON output" section: practical `jq`
  one-liners (top-N biggest files, errors only, count by code,
  fail-on-AGT008 for CI) plus a Python snippet for jq-less setups.
- `pipx install` documented as the primary install path, so
  `claude-audit` works from any directory regardless of which project
  venv is active.

### Changed (BREAKING — headline metric semantics)
- The headline "Session-start cost" was renamed to **"Always loaded"** and
  now reflects what Claude Code actually pulls into the main session at
  startup: the full `CLAUDE.md`, the full `rules/`, plus only the YAML
  frontmatter of each agent and skill. Agent and skill *bodies* are
  reported separately as **"On-demand"** weight — they only enter
  context when invoked (sub-agents run in their own session; skills
  load body at use time). The previous metric overstated the real
  session-start load by roughly 8× on typical projects and is being
  retired. `Window occupation` is now driven by the always-loaded
  figure, so the percentage actually reflects what competes for the
  context window at startup.
- The Categories panel in the HTML report now shows the eager/on-demand
  split per source, and the JSON output exposes `eager_load_total_tokens`,
  `on_demand_total_tokens`, and `total_config_tokens` (the legacy
  `session_start_total_tokens` field is retained as an alias of the
  eager total).

### Added
- GitHub Actions CI: runs the pytest suite on Python 3.10, 3.11, and 3.12
  for every push to `main` and every pull request. Status badge in the README.
- Self-contained sample HTML report at `examples/sample-audit.html`,
  linked from the README so visitors can preview the output without
  cloning the repo.
- HTML dashboard (`--html PATH`) with severity-coloured KPI cards, a
  stacked window-utilization chart that visualises overrun past the
  100% line, expandable file list (native `<details>`), and a
  light/dark/auto theme toggle persisted in `localStorage`.
- `NO_COLOR` environment variable support
  ([no-color.org](https://no-color.org/) convention) for suppressing
  ANSI color in terminal output without passing `--no-color`.
- Bidirectional emission for agent description overlaps (AGT008):
  both sides of an overlapping pair now receive a finding, not just one.

### Changed
- File→token counts are computed once per audit and cached in
  `BudgetReport.tokens_by_path`; the agent, skill, and health checks
  read from that map instead of re-invoking the tokenizer.
- `health.py` thresholds (window-percent warning/info levels, the
  large-CLAUDE.md cutoff, the agent/skill imbalance floor) are now
  named module constants.
- The scanner's directory skip-list is now a module-level constant
  with broader coverage: Rust (`target`), Go/PHP/Ruby (`vendor`), iOS
  (`Pods`), Android (`.gradle`), Next.js/Nuxt, IDE state directories,
  Terraform state, and additional Python cache directories.
- Terminal and HTML reports now agree on the same `TOP_FILES = 20`
  cutoff for the "largest files" section; the HTML wraps remaining
  rows in an expand-to-see-rest control.

## [0.1.0] — 2026-05-17

Initial Phase 1 release.

### Added
- Read-only auditor for `.claude/` and `CLAUDE.md`.
- Token estimator: `tiktoken` `cl100k_base` when available, character
  heuristic fallback otherwise. Both are clearly labelled as estimates
  in every report.
- Per-category breakdown (CLAUDE.md, agents, skills, rules) and a
  session-start total compared against a 200k reference context window.
- Agent quality checks (AGT001–AGT008): YAML parseability, required
  fields, `description` length bounds, token bloat, cross-agent
  description overlap via Jaccard similarity.
- Skill quality checks (SKL001–SKL005): SKILL.md frontmatter, required
  fields, description length bounds, token bloat.
- Health checks (HLT001–HLT006): per-file CLAUDE.md budget, session-start
  total versus window, and imbalance heuristics.
- Three output formats: coloured terminal (auto-disables for non-TTY),
  `--json` for machine consumption, and `--html PATH` for a static dashboard.
- CI-friendly `--fail-on` flag (`never` | `error` | `warning`).
- Strict read-only guarantee, verified by a test that snapshots every
  tracked file before and after an audit.
- Test suite (24 tests) covering scanner, token math, CLI exit codes,
  HTML output, and the read-only guarantee.
