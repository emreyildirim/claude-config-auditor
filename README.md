# claude-config-auditor

[![tests](https://github.com/emreyildirim/claude-config-auditor/actions/workflows/tests.yml/badge.svg)](https://github.com/emreyildirim/claude-config-auditor/actions/workflows/tests.yml)

A read-only linter for `.claude/` and `CLAUDE.md`. Measures the **token cost** your Claude Code config pays on every session, and audits **agent / skill quality** (missing descriptions, overlapping routes, broken YAML).

Think of it as ESLint for your context window.

## Why this exists

Claude Code loads `CLAUDE.md`, every `.claude/agents/*.md`, and every skill's `SKILL.md` into the context window on every session start. That's a **fixed per-session tax** — and most projects don't know how big theirs is.

The ecosystem has a lot of "session handoff" and "state management" tools. It doesn't have a linter for the config itself. This is that linter.

- "How many tokens does my CLAUDE.md actually cost?"
- "Are two of my agents describing the same job?" (Claude routes by description; near-duplicates cause silent misrouting.)
- "Is my SKILL.md description too vague for Claude to ever invoke it?"

## What it does (Phase 1)

- Counts tokens for `CLAUDE.md`, every agent, every skill, every rule, and every slash command.
- Splits the cost into **always-loaded** (full CLAUDE.md + full rules + agent/skill *frontmatter*) and **on-demand** (agent/skill *bodies* + slash commands, loaded when the agent runs, the skill is invoked, or the user types `/<command>`). The always-loaded number is what actually competes for context-window space at session start.
- Reports both numbers and the always-loaded share of a typical 200k window.
- Lints agent and skill frontmatter (missing fields, descriptions that are too short or too long, malformed YAML). Per-file *eager footprint* checks (AGT007 / SKL005) flag the kind of bloat that costs you on every session, not just files that happen to be large.
- Detects overlapping agent `description` fields by simple word-overlap.
- Recognises common third-party framework installs (BMAD, claude-flow, agent-pack / skill-pack / command-pack shapes) and adds that context to relevant findings so a missing CLAUDE.md is read as "intentional, ignore if it suits you" rather than scolding.
- Outputs a human-readable terminal report, JSON (`--json`), or a self-contained HTML report with charts (`--html`).
- **Never modifies any files.** Phase 1 is strictly read-only.

## What it does *not* do (yet)

- It does not rewrite or shorten anything for you — that's Phase 2.
- It does not call the Claude API. Phase 1 runs fully offline.
- It does not hook into a live session.

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

# Install the auditor:
pipx install git+https://github.com/emreyildirim/claude-config-auditor.git

# Optional: closer token estimates via tiktoken.
pipx inject claude-config-auditor tiktoken
```

After that, `claude-audit --help` works from any project directory.

### From source (for contributing)

```bash
git clone https://github.com/emreyildirim/claude-config-auditor.git
cd claude-config-auditor

python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'    # editable install + pytest + tiktoken

pytest                      # run the test suite
claude-audit --help         # verify it works
```

## Use

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
```

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

**No.** Phase 1 — the only mode currently shipping — is strictly
read-only. There is an automated test (`test_auditor_does_not_modify_target`)
that snapshots every file's mtime and size before and after a full
audit run; the suite fails if anything changes.

The HTML report writer refuses to write inside the audited target
directory at all; you have to pass it an output path elsewhere. The
auditor itself never creates files in the project being audited.

Phase 2 (planned) will add an opt-in `fix` mode that can modify files —
but only after showing every change as a diff, taking your explicit
confirmation, and backing up the original. That work lives on a
separate branch and is not part of any release yet.

### Why are the token counts called "estimates"?

Anthropic does not publish the Claude 3+/4 tokenizer's vocabulary, so
no fully-offline tool can compute an exact count. The auditor uses
either `tiktoken` with the `cl100k_base` encoding (OpenAI's GPT-4
tokenizer — empirically within ~10-15% of Anthropic's count for
English / Markdown) or a character-based heuristic as a fallback. The
report explicitly names which method was used so the uncertainty is
visible.

If Anthropic publishes a vendored tokenizer or a `count_tokens` model
suitable for offline use, we'll wire it in and the numbers will sharpen.

## Roadmap

- **Phase 1 — current:** read-only analysis and reporting.
- **Phase 2 — planned:** suggested fixes and opt-in `CLAUDE.md` rewriting.

## License

MIT — see [LICENSE](LICENSE).
