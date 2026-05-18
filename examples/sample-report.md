# Sample report — clean fixture

Output from running `claude-audit` on `tests/fixtures/good`. The fixture
contains a small CLAUDE.md, two non-overlapping agents, and one skill.

```
claude-config-auditor  target: tests/fixtures/good
tokenizer: tiktoken-cl100k_base

Session-start fixed cost
  ~410 tokens  (0.2% of 200k (typical Claude Code default))
  This is paid on every Claude Code session in this project.

By category
  claude.md    1 file(s)   ~80 tokens
  agent        2 file(s)   ~225 tokens
  skill        1 file(s)   ~105 tokens

Largest files (top 15)
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

---

# Sample report — broken fixture

Same tool, same flags, on `tests/fixtures/broken`. This fixture is wired
to trigger every kind of finding the auditor knows about.

```
claude-config-auditor  target: tests/fixtures/broken
tokenizer: tiktoken-cl100k_base

Session-start fixed cost
  ~241 tokens  (0.1% of 200k (typical Claude Code default))
  This is paid on every Claude Code session in this project.

By category
  claude.md    1 file(s)   ~19 tokens
  agent        5 file(s)   ~191 tokens
  skill        1 file(s)   ~31 tokens

Largest files (top 15)
  ~    53 tok  agent       .claude/agents/overlap-a.md
  ~    44 tok  agent       .claude/agents/overlap-b.md
  ~    39 tok  agent       .claude/agents/bad-yaml.md
  ~    31 tok  skill       .claude/skills/no-frontmatter-skill/SKILL.md
  ~    30 tok  agent       .claude/agents/no-description.md
  ~    25 tok  agent       .claude/agents/short-desc.md
  ~    19 tok  claude.md   CLAUDE.md

Findings  3 error  2 warning  0 info
  error   [AGT001] .claude/agents/bad-yaml.md
          frontmatter could not be parsed (invalid YAML)
          hint: Fix the YAML between the '---' lines at the top of the file.
  error   [AGT003] .claude/agents/no-description.md
          missing required field `description` in frontmatter
          hint: Claude routes to agents by description text. An empty
                description means this agent will never fire.
  error   [SKL001] .claude/skills/no-frontmatter-skill/SKILL.md
          SKILL.md frontmatter could not be parsed (no '---' delimiter)
          hint: Fix the YAML between the '---' lines at the top of SKILL.md.
  warning [AGT008] .claude/agents/overlap-a.md
          description overlaps with `.claude/agents/overlap-b.md`
          (word-overlap 93%)
          hint: Overlapping descriptions cause Claude to pick the wrong agent.
  warning [AGT004] .claude/agents/short-desc.md
          `description` is very short (4 chars)
          hint: Short descriptions make routing unreliable.
```
