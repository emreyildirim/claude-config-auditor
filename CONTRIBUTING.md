# Contributing

Thanks for poking around the repo. This document covers the practical
side: how to get the tool running locally, where the code lives, and
what to keep in mind when sending a PR.

## Setup

Requires Python 3.10+. Recommended: a virtual environment so the
package's dependencies don't pollute system Python.

```bash
git clone https://github.com/emreyildirim/claude-config-auditor.git
cd claude-config-auditor

python3 -m venv .venv
source .venv/bin/activate

# Install with the dev extras (pytest + tiktoken).
pip install -e '.[dev]'
```

After that, `claude-audit` is on `PATH` for the lifetime of the venv:

```bash
claude-audit .                  # audit the current directory
claude-audit ~/some-project --html /tmp/report.html
```

## Running the tests

```bash
pytest                          # full suite
pytest tests/test_jaccard.py    # one file
pytest -k overlap               # tests matching a keyword
pytest -v                       # verbose, shows every test name
```

Tests live under `tests/`. Fixtures (intentionally-good and
intentionally-broken `.claude/` directories) live under
`tests/fixtures/`.

The CI workflow runs the same `pytest` command on Python 3.10, 3.11,
and 3.12 in parallel on every push and pull request.

## Code layout

```
src/claude_config_auditor/
├── scanner.py        # walks the target and reads files
├── tokens.py         # token estimation (the most isolated module —
│                     # this is the piece most likely to change as
│                     # Anthropic publishes more tokenizer info)
├── findings.py       # the Finding / Severity types shared by checks
├── checks/
│   ├── budget.py     # token cost totals and category breakdown
│   ├── agents.py     # agent quality (AGT001–AGT008)
│   ├── skills.py     # skill quality (SKL001–SKL005)
│   └── health.py     # cross-cutting health checks (HLT001–HLT006)
├── report.py         # terminal + JSON renderers
├── render_html.py    # self-contained HTML dashboard
└── cli.py            # argument parsing and orchestration
```

## Design principles to preserve

These are the load-bearing assumptions; please don't break them without
discussing first.

1. **The auditor is strictly read-only on the target.** The test
   `test_auditor_does_not_modify_target` snapshots every file's mtime
   and size before and after an audit and asserts they're identical.
   `--html` writes its report file outside the target dir (the CLI
   refuses paths inside the target).
2. **Token counts are estimates and we say so loudly.** Anthropic does
   not publish the Claude 3+ tokenizer, so any offline count is an
   approximation. Every output names the method used and includes a
   note explaining the uncertainty.
3. **Findings carry codes (`AGT001`, `SKL003`, etc.).** Codes are
   contract: tests and downstream tooling key off them. If you add a
   new check, allocate a fresh code in the same prefix family. Don't
   reuse retired codes.
4. **Token counts are computed once per audit.** `BudgetReport.tokens_by_path`
   is the single source of truth; downstream checks (`agents`, `skills`,
   `health`) read from it instead of invoking the tokenizer.

## Adding a new check

Most new work fits this pattern. Example: add a check for "skill name
matches its directory name".

1. Decide the severity (`error`, `warning`, `info`) and the next free
   code in the prefix (`SKL006`, here).
2. Add the check logic to the appropriate `checks/*.py` module.
3. Add a fixture under `tests/fixtures/broken/` (or extend an existing
   one) that triggers the new finding.
4. Add a test that asserts the new code appears for that fixture.
5. Update `CHANGELOG.md` under `[Unreleased] → Added`.

## Sending a pull request

- Run `pytest` locally before pushing. CI will catch failures anyway,
  but a clean local run keeps the review focused on intent rather
  than red checkmarks.
- One commit per logical change; squash trivial fixups before opening
  the PR.
- Commit messages describe *why* the change is needed, not just *what*
  changed — the diff already shows what changed. The existing log is
  the format guide.
- The PR description should explain the user-visible effect and link
  any related discussion.

## Reporting issues

Bug reports are welcome under
[Issues](https://github.com/emreyildirim/claude-config-auditor/issues).
Useful detail to include:

- The exact `claude-audit` command you ran.
- The Python version (`python --version`).
- Whether you have `tiktoken` installed (`pip show tiktoken`).
- A minimal `.claude/` layout that reproduces the problem, if possible.
