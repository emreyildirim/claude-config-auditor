# Sample `fix` dry-run output

Output from:

```bash
claude-audit fix ~/example-project --dry-run --no-color
```

The fixture deliberately has the three findings the proposer can act on:
two agents whose descriptions overlap (AGT008, bidirectional), and a
CLAUDE.md with a long `## Changelog` section. The proposer collapses
the overlap pair into one proposal per affected file and emits a
single archive proposal for the changelog.

`--dry-run` shows every diff and a `(dry-run — not applied)` footer.
Nothing is prompted, nothing is written, no backup is opened.

```
[1/3] Annotate unity-specialist.md with description hints  (AGT008)
───────────────────────────────────────────────────────────────────
  rationale: Phase 1 flagged this agent for AGT008. The auditor cannot
             rewrite descriptions reliably without semantic context, so
             it inserts TODO comments pointing at what to revise.
  file:      ~/example-project/.claude/agents/unity-specialist.md
  change:    +3 / -0 line(s)

--- a/.claude/agents/unity-specialist.md
+++ b/.claude/agents/unity-specialist.md
@@ -1,5 +1,8 @@
 ---
 name: unity-specialist
+# TODO (claude-audit, AGT008): description overlaps with
+# `.claude/agents/unreal-specialist.md` (word-overlap 93%).
+# Add a disambiguator: say what this agent does that the other one does NOT.
 description: Reviews pull requests for code quality, naming, and obvious bugs…
 ---
 body

  (dry-run — not applied)

[2/3] Annotate unreal-specialist.md with description hints  (AGT008)
────────────────────────────────────────────────────────────────────
  ...same shape, mirroring the other side of the overlap...

[3/3] Archive 1 section(s) of CLAUDE.md → CLAUDE.archive.md  (HLT001)
─────────────────────────────────────────────────────────────────────
  rationale: Each section below looks unlikely to be needed in every
             Claude Code session. Sections selected: `## Changelog`
             (heading suggests reference/log content). They move into
             CLAUDE.archive.md; pointers stay in the source so you can
             always find them again.
  affects 2 file(s):
    new   ~/example-project/CLAUDE.archive.md  (+12 / -0)
    edit  ~/example-project/CLAUDE.md          (+2 / -8)

--- /dev/null
+++ b/CLAUDE.archive.md
@@ -0,0 +1,12 @@
+<!-- moved from CLAUDE.md by claude-config-auditor -->
+
+## Changelog
+
+- 2026-01-01: release 1. Lots of small fixes and improvements …
+- 2026-02-01: release 2. More improvements and the kitchen sink.
+…

--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -7,8 +7,2 @@
 
 ## Changelog
 
-- 2026-01-01: release 1. Lots of small fixes and improvements …
-- 2026-02-01: release 2. More improvements and the kitchen sink.
-…
+*Moved to [CLAUDE.archive.md](./CLAUDE.archive.md).*

  (dry-run — not applied)
```

## Interactive run (without `--dry-run`)

The same three proposals, but after each diff:

```
  Apply this change? [y]es / [n]o / [a]ll / [q]uit > _
```

- `y` — apply this one, move on to the next.
- `n` — skip this one.
- `a` — apply this one and every remaining proposal without prompting.
  Diffs are still printed; this is batch consent, not silent application.
- `q` — stop. No further proposals are considered.

After the loop, a single line summarises what was applied and where the
backup landed:

```
Applied 3 change(s). Backup written to /…/.claude-config-auditor/backups/2026-05-19T11-56-05Z-7ee17f
```

## Reverting

```
$ claude-audit revert ~/example-project --list
1 backup session(s):
  2026-05-19T11-56-05Z-7ee17f

$ claude-audit revert ~/example-project
Reverted 4 file(s) from session 2026-05-19T11-56-05Z-7ee17f.
```

If a file has been hand-edited since the fix, revert refuses to
overwrite it:

```
error: file has drifted since fix applied: …/CLAUDE.md
       (expected sha 6f1c8a3b…, found 2dafa7b1…).
Re-run with --force to overwrite the drifted file(s) anyway.
```

## Where backups live

```
~/example-project/.claude-config-auditor/
└── backups/
    └── 2026-05-19T11-56-05Z-7ee17f/
        ├── manifest.json   ← lists every file with sha_before / sha_after
        └── files/
            ├── CLAUDE.md
            └── .claude/agents/unity-specialist.md
            └── …
```

The directory is plain-text and discoverable — `ls -a` shows it next
to your `.claude/`, and `cat .../manifest.json` walks you through what
changed. Backups are intentionally not deleted by the tool; you remove
them yourself with `rm -rf` when you're done.
