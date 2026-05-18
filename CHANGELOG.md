# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
