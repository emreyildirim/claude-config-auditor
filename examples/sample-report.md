# Sample report — clean fixture

Output from running `claude-audit` on `tests/fixtures/good`. The fixture
contains a small CLAUDE.md, two non-overlapping agents, and one skill.

```
claude-config-auditor  target: tests/fixtures/good
tokenizer: tiktoken-cl100k_base

Always-loaded session footprint
  ~256 tokens  (0.1% of 200k (typical Claude Code default))
  + ~154 tokens on-demand (agent/skill bodies, loaded when invoked)
  The always-loaded figure is paid on every Claude Code session.

By category  (eager / on-demand / total)
  claude.md    1 file(s)   ~     80 /          — / ~80
  agent        2 file(s)   ~    117 /       ~108 / ~225
  skill        1 file(s)   ~     59 /        ~46 / ~105

Largest files (top 20)
  ~   117 tok  agent       .claude/agents/security-reviewer.md
  ~   108 tok  agent       .claude/agents/code-reviewer.md
  ~   105 tok  skill       .claude/skills/example-skill/SKILL.md
  ~    80 tok  claude.md   CLAUDE.md

Findings  0 error  0 warning  0 info
  No issues found.

Estimated using tiktoken `cl100k_base` (OpenAI GPT-4 tokenizer).
Anthropic does not publish the Claude tokenizer; this is a
close-but-not-exact proxy. Treat numbers as ±10-15%.
This tool is read-only. Nothing was modified.
```

Two columns matter on the headline line:

- **Always loaded** — what Claude pulls into the main session at startup:
  full CLAUDE.md, full rules, plus the frontmatter of every agent and
  skill. This is what actually fights for context-window space.
- **On-demand** — agent and skill *bodies*. Loaded only when the agent
  runs (as a sub-session) or the skill is invoked. Not in the main
  session prompt, but worth knowing about for total token spend.

---

# Sample report — broken fixture

The broken fixture is wired to trigger every category of finding.

```
Findings  3 error  2 warning  0 info
  error   [AGT001]  bad-yaml.md — frontmatter could not be parsed
  error   [AGT003]  no-description.md — missing `description` field
  error   [SKL001]  no-frontmatter-skill — SKILL.md missing frontmatter
  warning [AGT008]  overlap-a.md — overlaps with overlap-b.md (93%)
  warning [AGT008]  overlap-b.md — overlaps with overlap-a.md (93%)
  warning [AGT004]  short-desc.md — `description` is very short (4 chars)
```

For the full HTML version, see [`sample-audit.html`](sample-audit.html).
