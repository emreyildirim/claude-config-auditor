# TODO

Ideas to consider, not yet planned into a phase. Each item is a one-line
title with the problem, a sketch of the options, and a short "decide
later" note. Keep entries terse — this file is a thinking pad, not a
specification.

---

## Easier global invocation (no absolute paths, no per-shell venv)

**Problem:** Right now you only get the `claude-audit` command when the
auditor's own `.venv` is the active environment. If you're in another
project's venv (which is the normal case), you have to either type the
absolute path `/Users/.../claude-config-auditor/.venv/bin/claude-audit`
or set up a shell alias by hand. The brief made this OK for Phase 1 ("a
tool you clone and run from"), but it's friction now that it's
actually being used across projects.

**Options to consider:**

1. **`pipx install .` (recommended starter):** installs the tool into
   its own isolated venv that pipx places on `PATH`. Survives other
   venv activations. One command, no shell mess. Drawback: requires
   the user to have pipx — but `pipx` is a one-time `brew install
   pipx` or `python -m pip install --user pipx`.
2. **Editable user install (`pip install --user -e .`):** drops the
   entry point into `~/.local/bin/`. Lighter than pipx but pollutes
   the user site-packages.
3. **Publish to PyPI:** `pip install claude-config-auditor` from
   anywhere. Phase 3+ when the API is stable.
4. **Wrapper script + symlink:** add a `bin/claude-audit` to the repo
   and symlink it into `/usr/local/bin`. Cheap but feels old-school.
5. **`Justfile` or `Makefile` recipes:** `just audit ~/project` ⇒
   forwards to the venv binary. Only useful when invoking from the
   auditor repo, not from arbitrary cwd.

**Recommendation when revisited:** start with pipx — best UX for the
"install once, use everywhere" story; works for friends cloning the
repo and Phase 2 testers.

**Status:** noted, not started.

---
