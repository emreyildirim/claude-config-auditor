# claude-config-auditor

[![tests](https://github.com/emreyildirim/claude-config-auditor/actions/workflows/tests.yml/badge.svg)](https://github.com/emreyildirim/claude-config-auditor/actions/workflows/tests.yml)

A **non-destructive** linter and cost auditor for `.claude/` and `CLAUDE.md` — *we annotate, we don't rewrite*. Measures the **token cost** your Claude Code config pays on every session, and audits **agent / skill quality** (missing descriptions, overlapping routes, broken YAML).

Think of it as ESLint for your context window.

## Why this exists

Claude Code loads `CLAUDE.md`, every `.claude/agents/*.md`, and every skill's `SKILL.md` into the context window on every session start. That's a **fixed per-session tax** — and most projects don't know how big theirs is.

The ecosystem has a lot of "session handoff" and "state management" tools. It doesn't have a linter for the config itself. This is that linter.

- "How many tokens does my CLAUDE.md actually cost?"
- "Are two of my agents describing the same job?" (Anthropic's docs say agents are selected based on their description; the exact ranking algorithm isn't published, but overlapping descriptions create routing ambiguity in practice.)
- "Is my SKILL.md description too vague for Claude to ever invoke it?"

## Cost snapshot — six popular frameworks

The headline `claude-audit --html` numbers from a clean May 2026
install of six popular Claude Code frameworks:

| Framework                  | Always loaded | Window  | Files | Findings |
|----------------------------|--------------:|--------:|------:|---------:|
| SuperClaude                |   591 tok     | 0.3%    |  51   | 3        |
| wshobson                   | 1,275 tok     | 0.6%    |  29   | 1        |
| BMAD                       | 3,066 tok     | 1.5%    |  70   | 2        |
| claude-flow                | 7,474 tok     | 3.7%    | 217   | 33       |
| VoltAgent                  | 10,010 tok    | 5.0%    | 145   | 1        |
| Claude-Code-Game-Studios   | 17,858 tok    | 8.9%    | 138   | 3        |

**"Always loaded"** is what Claude actually pulls into the main
session at startup — full `CLAUDE.md` + full `rules/` + only the YAML
frontmatter of every agent and skill. **"Window"** is that figure
expressed as a percentage of a 200k reference context window.
**"Findings"** is the count of agent / skill / health issues the
auditor flagged.

The 0.3% → 8.9% spread is informative on its own. A lean framework
audits quietly; a heavy one flags exactly where to thin down. Full
HTML reports — open in any browser, no network — live under
[`case-studies/`](case-studies/).

## What it does

Two modes — `audit` is the default and is read-only; `fix` is opt-in
and prompts before every change.

**`audit` (default, read-only)**

- Counts tokens for `CLAUDE.md`, every agent, every skill, every rule, and every slash command.
- Splits the cost into **always-loaded** (full CLAUDE.md + full rules + agent/skill *frontmatter*) and **on-demand** (agent/skill *bodies* + slash commands, loaded when the agent runs, the skill is invoked, or the user types `/<command>`). The always-loaded number is what actually competes for context-window space at session start.
- Reports both numbers and the always-loaded share of a typical 200k window.
- Lints agent and skill frontmatter (missing fields, descriptions that are too short or too long, malformed YAML). Per-file *eager footprint* checks (AGT007 / SKL005) flag the kind of bloat that costs you on every session, not just files that happen to be large.
- Detects overlapping agent `description` fields by simple word-overlap.
- Recognises common third-party framework installs (BMAD, claude-flow, agent-pack / skill-pack / command-pack shapes) and adds that context to relevant findings so a missing CLAUDE.md is read as "intentional, ignore if it suits you" rather than scolding.
- Outputs a human-readable terminal report, JSON (`--json`), or a self-contained HTML report with charts (`--html`).
- **Never modifies any files.** Verified by an automated mtime/size snapshot test.

**`fix` (opt-in, prompts before every change)**

- Walks fixable findings one by one: rationale → unified diff → +/- summary → explicit y/n/a/q prompt.
- Two proposers shipped today: agent-description fixes for `AGT003`–`AGT008` (annotates frontmatter with `# TODO` YAML comments — Claude ignores them so behaviour is unchanged the moment the fix applies), and CLAUDE.md archive (moves stale sections into a sibling `CLAUDE.archive.md` using conservative veto heuristics).
- Every accepted change is backed up with SHA-256 manifests; `claude-audit revert` restores any session and refuses to overwrite hand-edited files unless `--force` is passed.
- `--dry-run` previews without writing; `--apply-all` batches approval (still prints every diff) for non-interactive use.

## What it does *not* do

- It does not call the Claude API. Everything is offline.
- It does not hook into a live session.
- It does not silently modify your files. `audit` is read-only; `fix`
  is opt-in and prompts before every change.

## Design principles — why we annotate, not rewrite

Unlike LLM-autofix linters in this space, this tool refuses to invent
agent / skill description text on a developer's behalf. The `fix` mode
either *annotates* (inserts a discoverable `# TODO` marker above the
field that needs work) or *moves content mechanically* (relocating a
stale CLAUDE.md section into a sibling archive). It never produces new
prose. Five reasons that's the contract:

1. **Predictability.** A given finding produces the same diff every
   time. The auditor is a function, not a probabilistic generator —
   `claude-audit fix --dry-run` today and a month later show the same
   output for the same input.
2. **Reversibility.** Every applied change is backed up with a
   SHA-256 manifest, and `revert` refuses to overwrite hand-edits
   unless `--force` is passed. The smaller and more mechanical the
   change, the more meaningful "revert" is — a one-line YAML comment
   reverts cleanly; an LLM rewrite that touched a dozen tokens does
   not.
3. **No API key, no network, no per-run cost.** The tool runs
   offline by default. Nothing about your config is uploaded to a
   third party. (The optional `--accurate` flag described below is
   the single, explicit opt-out and it never changes default
   behaviour.)
4. **No model-version drift.** Heuristics are pinned and live in this
   repo. An LLM-based linter's output depends on whichever model
   version it happens to call — same project, different month,
   different fix.
5. **Human-in-the-loop by design.** Writing an agent's `description:`
   is a product decision (it shapes how Claude routes to it). A linter
   should surface the problem, not impersonate the developer making
   that call.

The roadmap sticks to this contract. The default `fix` behaviour does
not change.

## Install

Requires Python 3.10+ on the machine running the auditor. The target
project can be in any language — the auditor only reads Markdown and
YAML, never executes target code (see [FAQ](#faq) below).

### Recommended: pipx (one-time install, works everywhere)

[pipx](https://pipx.pypa.io/) installs Python CLI tools into isolated
virtual environments and puts the executables on your `PATH`. The
`claude-audit` command then works from any directory, regardless of
which project venv you happen to have active.

```bash
# One-time: install pipx itself if you don't have it.
brew install pipx        # macOS
# or:  python3 -m pip install --user pipx  &&  pipx ensurepath

# Install the auditor (tiktoken comes with it as a hard dependency).
pipx install git+https://github.com/emreyildirim/claude-config-auditor.git
```

After that, `claude-audit --help` works from any project directory.

### From source (for contributing)

```bash
git clone https://github.com/emreyildirim/claude-config-auditor.git
cd claude-config-auditor

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'    # editable install + pytest (tiktoken comes from the base deps)

pytest                      # run the test suite
claude-audit --help         # verify it works
```

### Use as a pre-commit hook

The repo ships a [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml) so
the auditor can be wired into the
[pre-commit](https://pre-commit.com/) framework directly. Add to your
project's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/emreyildirim/claude-config-auditor
    rev: main   # pin to a tag or SHA in real usage
    hooks:
      - id: claude-audit
        args: [--fail-on, error]
```

Then `pre-commit install` registers the hook. It runs only when files
under `.claude/` or `CLAUDE.md` change, exits non-zero on blocking
findings (so the commit is rejected), and stays silent otherwise. The
`--fail-on` flag controls how strict the gate is: `error` (default
recommendation) blocks only on real problems; `warning` is stricter;
`never` makes the hook informational.

## Use

The tool has three subcommands. The first two — `audit` (default) and
any of the flag-only invocations — are **strictly read-only**. The
third — `fix` — is **opt-in** and asks before every change.

### `audit` — read-only report

```bash
# Audit the current directory.
claude-audit

# Audit a specific project.
claude-audit ~/code/my-project

# Machine-readable output.
claude-audit --json > report.json

# Standalone HTML report with charts (opens offline, no network).
claude-audit ~/code/my-project --html report.html

# Fail in CI when there are blocking issues.
claude-audit --fail-on warning

# Custom CLAUDE.md token budget (default 5000).
claude-audit --budget 3000

# Route token counts through Anthropic's count_tokens endpoint for
# ground-truth accuracy. Opt-in only; requires ANTHROPIC_API_KEY in
# the environment. Per-file results are cached at
# ~/.cache/claude-config-auditor/ so repeat audits don't re-hit the API.
ANTHROPIC_API_KEY=sk-ant-... claude-audit --accurate

# Pin the model used for count_tokens (default: claude-sonnet-4-5).
claude-audit --accurate --accurate-model claude-haiku-4-5
```

`audit` never modifies any file. The default behaviour stays this way
forever — Phase 2 was deliberately put behind an explicit subcommand.

### `fix` — propose and apply changes (Phase 2, opt-in)

Walks you through fixable findings. For each one you see:

- a one-line rationale,
- a unified diff of what would change (red for removals, green for adds),
- a per-file +/- summary,
- and an explicit prompt: `[y]es / [n]o / [a]ll-remaining / [q]uit`.

Everything applied is backed up under
`.claude-config-auditor/backups/<timestamp>/` inside the target. Revert
is one command away.

```bash
# Preview without prompting or writing anything (safest first step).
claude-audit fix . --dry-run

# Interactive: see diff, answer y/n/a/q per change.
claude-audit fix .

# Batch approval (still prints every diff, just skips the per-change
# prompt). Required when stdin is not an interactive terminal (CI).
claude-audit fix . --apply-all

# Put backups somewhere else (default is inside the target).
claude-audit fix . --backup-dir ~/backups/
```

What `fix` can currently propose:

- **Annotate weak / overlapping agent descriptions** (codes
  `AGT003` – `AGT008`). Inserts `# TODO (claude-audit, AGTxxx)` YAML
  comments above the `description:` field. Claude ignores these at
  load time, so behaviour is unchanged the moment the fix applies; the
  TODO marks where you need to revise.
- **Move stale CLAUDE.md sections into a sibling archive** (code
  `HLT001`). Conservative heuristics: protected headings (Rules,
  Conventions, …) and sections with operational language ("always",
  "must", "before using", …) are never archived. Each moved section
  leaves a pointer in the source so the outline survives.

The two proposers ship intentionally different philosophies.
`agent_description` **annotates** — the TODO marker is a grep-friendly
hint, the description text itself is left untouched on purpose, because
the auditor will not invent wording on a developer's behalf.
`claude_md_archive` **edits** — a section is physically moved into a
sibling file because the operation is mechanical and reversible. A
future Phase 3 may add LLM-assisted description rewriting on top of
the existing annotation; for now, the split is the contract.

Example dry-run output is at
[`examples/sample-fix-output.md`](examples/sample-fix-output.md).

### `revert` — undo a fix run

```bash
# Enumerate backup sessions for a target.
claude-audit revert . --list

# Restore the most recent session.
claude-audit revert .

# Restore a specific session by id.
claude-audit revert . 2026-05-19T11-56-05Z-7ee17f

# If you've hand-edited the fix's output and want to overwrite anyway.
claude-audit revert . --force
```

`revert` checks each file's SHA-256 against what was on disk when the
fix completed. If a file has drifted (you edited it between apply and
revert), the revert is refused — your later edits are not silently
destroyed. `--force` opts out of this check.

### Safety guarantees (still true with `fix` in the picture)

- `audit` never touches a file. The automated test
  `test_auditor_does_not_modify_target` snapshots every file's mtime
  and size before and after a full run and asserts they're identical.
- `fix` never empties or deletes a file. Proposals can edit existing
  files or create new ones; an "empty after" is rejected at the data
  model.
- Every applied change is backed up plain-text and discoverable.
  `.claude-config-auditor/backups/<id>/manifest.json` lists every file
  touched, with SHA-256 before and after.
- The HTML report writer refuses to write inside the audited target.

## Example output

- **Terminal:** [`examples/sample-report.md`](examples/sample-report.md) — annotated terminal output from clean and broken fixtures.
- **HTML dashboard:** [`examples/sample-audit.html`](examples/sample-audit.html) — full HTML report (download to open offline, or view raw on GitHub). Light/dark theme, expandable file list, severity-coloured findings, hover tooltips on every metric.

Quick terminal taste:

```
Always-loaded session footprint
  ~256 tokens  (0.1% of 200k (typical Claude Code default))
  + ~154 tokens on-demand (agent/skill bodies, loaded when invoked)
  The always-loaded figure is paid on every Claude Code session.

By category  (eager / on-demand / total)
  claude.md    1 file(s)   ~80 / — / ~80
  agent        2 file(s)   ~117 / ~108 / ~225
  skill        1 file(s)   ~59 / ~46 / ~105
  command      2 file(s)   ~0 / ~140 / ~140

Findings  0 error  0 warning  0 info
  No issues found.
```

Slash commands appear with `~0` eager weight because Claude Code does not pull `.claude/commands/*.md` into context until the user types `/<command>`.

## Case studies

Six real audits against popular Claude Code frameworks
(BMAD, claude-flow, SuperClaude, VoltAgent, wshobson,
Claude-Code-Game-Studios) live under
[`case-studies/`](case-studies/). Each file is the raw HTML report
`claude-audit --html` produced on a clean install in May 2026 — same
metric tuning the rest of the README refers to. Use them as a baseline
when re-running the auditor against a new release of one of these
frameworks, or as a sanity check that the tool produces sensible
numbers on a project you trust.

## Working with the JSON output

`--json` writes a machine-readable report to stdout. Pipe it to a file
or another tool. The full schema is in
[`examples/sample-report.md`](examples/sample-report.md); a few common
recipes follow.

Save a report:

```bash
claude-audit ~/some-project --json > report.json
```

Pretty-print and inspect top-level keys (requires [`jq`](https://stedolan.github.io/jq/)):

```bash
claude-audit ~/some-project --json | jq 'keys'
```

Just the headline numbers:

```bash
claude-audit ~/some-project --json | jq '{
  always_loaded: .eager_load_total_tokens,
  on_demand: .on_demand_total_tokens,
  window_pct: .percent_of_window
}'
```

Top 10 biggest files:

```bash
claude-audit ~/some-project --json | jq '.files[:10] | map({
  path: .relpath,
  tokens: .tokens,
  category
})'
```

Only the errors (blocking findings):

```bash
claude-audit ~/some-project --json |
  jq '.findings | map(select(.severity == "error"))'
```

Count findings by code (useful in CI dashboards):

```bash
claude-audit ~/some-project --json |
  jq '[.findings[] | .code] | group_by(.) |
      map({code: .[0], count: length})'
```

Fail the build only when there are AGT008 overlaps:

```bash
overlaps=$(claude-audit ~/some-project --json |
           jq '[.findings[] | select(.code=="AGT008")] | length')
if [ "$overlaps" -gt 0 ]; then
  echo "Agent description overlaps detected — fix before merging."
  exit 1
fi
```

Python (no `jq` needed):

```python
import json, subprocess
data = json.loads(subprocess.check_output(
    ["claude-audit", "/path/to/project", "--json"]
))
big = [f for f in data["files"] if f["tokens"] > 5_000]
for f in big:
    print(f["tokens"], f["relpath"])
```

## FAQ

### Does this work on non-Python projects? React, Vue, Go, Ruby, Rust…?

**Yes — any project, any stack.** The auditor only reads Markdown
(`CLAUDE.md`) and YAML (the frontmatter inside `.claude/agents/*.md`
and `.claude/skills/*/SKILL.md`). It never executes the target
project's code, never invokes `npm` / `cargo` / `go` / `bundle`, never
parses application source files.

The only requirement is that **the machine running the auditor** has
Python 3.10+ available. If you install via `pipx`, that Python lives
inside the pipx-managed venv and does not interact with whatever
runtime your project uses.

Concrete examples — all work without any extra setup:

```
my-react-app/    ← npm/Vite project; node_modules/ and .next/ are skipped
my-go-api/       ← go.mod project; vendor/ is skipped
rails-monolith/  ← Ruby on Rails; vendor/, tmp/ are not traversed
rust-cli/        ← Cargo project; target/ is skipped
iOS-app/         ← Xcode project; Pods/, Library/ are skipped
```

The scanner's directory skip-list covers Rust (`target`), Go/Ruby/PHP
(`vendor`), JS/TS (`node_modules`, `.next`, `.nuxt`, `.turbo`,
`.svelte-kit`), iOS (`Pods`), Android (`.gradle`, `.mvn`), Terraform
(`.terraform`), IDE state (`.idea`, `.vscode`), and the usual Python
caches.

### Will the auditor modify any of my files?

**Only if you explicitly run `claude-audit fix`.** The default invocation
(`claude-audit`, `claude-audit --json`, `claude-audit --html …`) is
strictly read-only — the automated test
`test_auditor_does_not_modify_target` snapshots every file's mtime and
size before and after a full audit run and fails the suite if anything
changes. The HTML report writer also refuses to write inside the
audited target directory; you must pass an output path elsewhere.

The Phase 2 `fix` subcommand (opt-in, never the default) can modify
files, but only after:

1. Showing each change as a unified diff with a per-file +/- summary.
2. Asking for explicit `[y]es / [n]o / [a]ll-remaining / [q]uit`
   approval per proposal. `--apply-all` batches the approval but
   still prints every diff first; nothing is ever applied silently.
3. Writing a full backup with SHA-256 manifests under
   `.claude-config-auditor/backups/<session>/`, so `claude-audit
   revert` can restore the project to its pre-fix state.

If you never type the literal word `fix`, no file in your project is
ever written to.

### Why are the token counts called "estimates"?

Anthropic does not publish the Claude 3+/4 tokenizer's vocabulary, so
no fully-offline tool can compute an exact count. By default the
auditor uses `tiktoken` with the `cl100k_base` encoding (OpenAI's
GPT-4 tokenizer) — empirically within ~5-10% of Anthropic's count for
the Markdown/YAML content the tool actually scans. If `tiktoken`
cannot be imported (a stripped-down CI image, a no-network install),
the auditor falls back to a character-based heuristic at ~4.5
chars/token (tuned against five popular Claude Code frameworks in
May 2026). The report explicitly names which method was used so the
uncertainty is visible.

To force the heuristic even when `tiktoken` is installed (useful for
benchmarking or for cross-machine comparisons where `tiktoken`
versions differ), set the env var:

```bash
CLAUDE_AUDIT_TOKENIZER=heuristic claude-audit ~/my-project
```

If Anthropic publishes a vendored tokenizer or a `count_tokens` model
suitable for offline use, we'll wire it in and the numbers will sharpen.

## Roadmap

- **Phase 1 — shipped:** read-only `audit` for `.claude/` and CLAUDE.md.
- **Phase 2 — shipped:** opt-in `fix` mode (annotates weak agent
  descriptions, archives stale CLAUDE.md sections) and `revert` with
  drift detection.
- **Phase 2.5 — shipped:** opt-in `--accurate` flag routes token counts
  through Anthropic's public `count_tokens` endpoint. Requires
  `ANTHROPIC_API_KEY` in the environment (hard error if missing — the
  flag is an explicit opt-in and refuses to silently fall back). Each
  unique `(text, model)` is counted once and cached under
  `~/.cache/claude-config-auditor/` so repeat audits don't re-hit the
  API. Default tokenizer remains `tiktoken` `cl100k_base`; nothing
  about the offline contract changes unless the flag is passed.

## License

MIT — see [LICENSE](LICENSE).
