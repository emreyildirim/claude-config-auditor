# claude-config-auditor

A read-only linter for `.claude/` and `CLAUDE.md`. Measures the **token cost** your Claude Code config pays on every session, and audits **agent / skill quality** (missing descriptions, overlapping routes, broken YAML).

Think of it as ESLint for your context window.

## Why this exists

Claude Code loads `CLAUDE.md`, every `.claude/agents/*.md`, and every skill's `SKILL.md` into the context window on every session start. That's a **fixed per-session tax** — and most projects don't know how big theirs is.

The ecosystem has a lot of "session handoff" and "state management" tools. It doesn't have a linter for the config itself. This is that linter.

- "How many tokens does my CLAUDE.md actually cost?"
- "Are two of my agents describing the same job?" (Claude routes by description; near-duplicates cause silent misrouting.)
- "Is my SKILL.md description too vague for Claude to ever invoke it?"

## What it does (Phase 1)

- Counts tokens for `CLAUDE.md`, every agent, every skill, every rule.
- Reports the **session-start fixed cost** and what % of a typical 200k context window it occupies.
- Lints agent and skill frontmatter (missing fields, descriptions that are too short or too long, malformed YAML).
- Detects overlapping agent `description` fields by simple word-overlap.
- Outputs a human-readable terminal report, JSON (`--json`), or a self-contained HTML report with charts (`--html`).
- **Never modifies any files.** Phase 1 is strictly read-only.

## What it does *not* do (yet)

- It does not rewrite or shorten anything for you — that's Phase 2.
- It does not call the Claude API. Phase 1 runs fully offline.
- It does not hook into a live session.

## Install

Requires Python 3.10+. The package is currently developed from source.

```bash
git clone <this-repo-url>
cd claude-config-auditor

python3 -m venv .venv
source .venv/bin/activate

# Install with the recommended tiktoken-based token estimator.
pip install -e '.[tokenizer]'

# Or, if you don't want tiktoken — the tool will fall back to a
# character-based heuristic (and clearly label it as such).
# pip install -e .
```

`claude-audit` is now on your `PATH` for as long as the venv is active.

To run the test suite while developing:

```bash
pip install -e '.[dev]'
pytest
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

See [`examples/sample-report.md`](examples/sample-report.md) for full output from both a clean and a deliberately broken fixture. Quick taste:

```
Session-start fixed cost
  ~410 tokens  (0.2% of 200k (typical Claude Code default))
  This is paid on every Claude Code session in this project.

By category
  claude.md    1 file(s)   ~80 tokens
  agent        2 file(s)   ~225 tokens
  skill        1 file(s)   ~105 tokens

Findings  0 error  0 warning  0 info
  No issues found.
```

## Honest notes on token counting

Anthropic does not publish the Claude 3+ tokenizer's vocabulary, so any fully-offline count is an approximation. This tool uses:

1. **tiktoken `cl100k_base`** when available (OpenAI's GPT-4 tokenizer, empirically within ~10–15 % of Anthropic's count for English/Markdown), or
2. **a character-based heuristic** as a fallback.

Either way, the report names the method it used. Treat numbers as estimates, not exact counts.

## Roadmap

- **Phase 1 — current:** read-only analysis and reporting.
- **Phase 2 — planned:** suggested fixes and opt-in `CLAUDE.md` rewriting.

## License

MIT — see [LICENSE](LICENSE).
