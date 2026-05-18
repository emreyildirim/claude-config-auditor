---
name: example-skill
description: Use when the user wants to format a dataset as a Markdown table from CSV or TSV input. Triggers include "make a markdown table", "format as md table", or any time the user pastes tabular data and asks for cleanup.
---

# Example Skill

Takes tabular data as input and outputs a GitHub-flavored Markdown table.

## Steps
1. Detect the delimiter.
2. Parse the rows.
3. Emit a Markdown table with column alignment.
