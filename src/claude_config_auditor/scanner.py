"""Discover and read .claude/ and CLAUDE.md files in a target directory.

The scanner is intentionally permissive: malformed YAML frontmatter,
missing fields, and unusual file layouts surface as warnings on the
file's record rather than raising. Phase 1 is read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileRecord:
    """A single file with frontmatter, body, and any parse warnings."""

    path: Path
    relpath: str
    raw: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    frontmatter_ok: bool = True
    parse_warning: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.raw.encode("utf-8"))


@dataclass
class Scan:
    """Everything found in a target directory."""

    root: Path
    claude_md_files: list[FileRecord] = field(default_factory=list)
    agents: list[FileRecord] = field(default_factory=list)
    skills: list[FileRecord] = field(default_factory=list)
    rules: list[FileRecord] = field(default_factory=list)
    commands: list[FileRecord] = field(default_factory=list)
    has_claude_dir: bool = False
    has_claude_md: bool = False

    @property
    def all_loaded_at_session_start(self) -> list[FileRecord]:
        """Files paid for on every session start: CLAUDE.md + agents + skills + rules.

        Agents in Claude Code are loaded into the system prompt at session
        start; skills register their metadata (description) at startup so
        the model can decide when to invoke them. Both contribute to the
        session-start token cost. The brief defines this as the headline
        metric. See section 5.1.

        Slash commands under .claude/commands/ are not in this list: they
        are loaded only when the user types the command, so they have no
        eager footprint. They are still tracked under `Scan.commands` so
        the report can surface them.
        """
        return [*self.claude_md_files, *self.agents, *self.skills, *self.rules]


# Files we never want to read (binary or noisy).
_SKIP_NAMES = {".DS_Store"}
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip"}

# Directories we don't recurse into when looking for CLAUDE.md.
# Covers common build artifacts, dependency vendor trees, IDE state, and
# language-specific output dirs across Python, JS/TS, Rust, Go, Ruby, PHP,
# iOS, Android, and infrastructure tooling.
_SKIP_DIRS = {
    # VCS
    ".git", ".hg", ".svn",
    # Editor / IDE
    ".idea", ".vscode",
    # Python
    ".venv", "venv", "env", "__pycache__", ".tox", ".nox",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    # JS/TS
    "node_modules", ".next", ".nuxt", ".turbo", ".svelte-kit",
    # Build outputs (multi-language)
    "build", "dist", "out", "target",
    # Test coverage
    "coverage", ".coverage", ".nyc_output",
    # Caches
    ".cache", ".parcel-cache",
    # Ruby / PHP / Go
    "vendor",
    # iOS / macOS
    "Pods",
    # Android / JVM
    ".gradle", ".mvn",
    # Infra
    ".terraform",
}


def scan(root: Path) -> Scan:
    """Walk the target directory and collect everything Claude would load."""
    root = root.resolve()
    result = Scan(root=root)

    # CLAUDE.md at root + any nested CLAUDE.md (sub-projects/monorepos).
    for md in _find_claude_mds(root):
        rec = _read_file(md, root)
        if rec is not None:
            result.claude_md_files.append(rec)
    result.has_claude_md = bool(result.claude_md_files)

    claude_dir = root / ".claude"
    if not claude_dir.is_dir():
        return result
    result.has_claude_dir = True

    agents_dir = claude_dir / "agents"
    if agents_dir.is_dir():
        for f in sorted(agents_dir.rglob("*.md")):
            rec = _read_file(f, root)
            if rec is None:
                continue
            _parse_frontmatter_into(rec)
            result.agents.append(rec)

    skills_dir = claude_dir / "skills"
    if skills_dir.is_dir():
        # A skill is a folder containing SKILL.md (plus optional assets).
        # We treat SKILL.md as the canonical file — that is what Claude reads
        # at session start to decide when to invoke the skill.
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            rec = _read_file(skill_md, root)
            if rec is None:
                continue
            _parse_frontmatter_into(rec)
            result.skills.append(rec)

    rules_dir = claude_dir / "rules"
    if rules_dir.is_dir():
        for f in sorted(rules_dir.rglob("*.md")):
            rec = _read_file(f, root)
            if rec is not None:
                result.rules.append(rec)

    # Slash commands. Each .md is a single command. Commands have YAML
    # frontmatter (description, allowed-tools, etc.) but are loaded only
    # when the user types `/<name>` — they do not eager-load. We still
    # track them so the report can show their count and total weight.
    commands_dir = claude_dir / "commands"
    if commands_dir.is_dir():
        for f in sorted(commands_dir.rglob("*.md")):
            rec = _read_file(f, root)
            if rec is None:
                continue
            _parse_frontmatter_into(rec)
            result.commands.append(rec)

    return result


def _find_claude_mds(root: Path) -> list[Path]:
    """Root CLAUDE.md + nested ones, skipping build/vendor/IDE dirs."""
    found: list[Path] = []
    for path in root.rglob("CLAUDE.md"):
        # Skip if any ancestor segment is in _SKIP_DIRS.
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        found.append(path)
    return sorted(found)


def _read_file(path: Path, root: Path) -> FileRecord | None:
    if path.name in _SKIP_NAMES or path.suffix.lower() in _SKIP_SUFFIXES:
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return FileRecord(
            path=path,
            relpath=str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
            raw="",
            frontmatter_ok=False,
            parse_warning=f"unreadable: {exc}",
        )
    return FileRecord(
        path=path,
        relpath=str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
        raw=raw,
        body=raw,
    )


def _parse_frontmatter_into(rec: FileRecord) -> None:
    """Parse `---\\n...\\n---` YAML frontmatter at the top of the file.

    Uses PyYAML if available, otherwise a minimal hand-rolled parser
    sufficient for the typical agent/skill frontmatter (flat key: value).
    """
    fm, body, warn = _split_frontmatter(rec.raw)
    rec.body = body
    if fm is None:
        # No frontmatter at all. Caller decides whether that is an error.
        rec.frontmatter = {}
        rec.frontmatter_ok = False
        rec.parse_warning = warn or "missing frontmatter"
        return

    parsed, perr = _parse_yaml(fm)
    if perr is not None:
        rec.frontmatter = {}
        rec.frontmatter_ok = False
        rec.parse_warning = perr
        return
    rec.frontmatter = parsed
    rec.frontmatter_ok = True


def _split_frontmatter(raw: str) -> tuple[str | None, str, str | None]:
    """Return (frontmatter_text, body_text, warning_if_any)."""
    if not raw.startswith("---"):
        return None, raw, "no '---' frontmatter delimiter at top of file"
    # Match first delimiter line.
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return None, raw, "no '---' frontmatter delimiter at top of file"
    # Find closing delimiter.
    for idx in range(1, len(lines)):
        if lines[idx].rstrip() == "---":
            fm_text = "".join(lines[1:idx])
            body_text = "".join(lines[idx + 1 :])
            return fm_text, body_text, None
    return None, raw, "frontmatter has no closing '---' delimiter"


def _parse_yaml(text: str) -> tuple[dict[str, Any], str | None]:
    """Parse YAML frontmatter. Prefer PyYAML; fall back to a minimal parser."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_yaml_minimal(text)

    try:
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001 — pyyaml raises a variety
        return {}, f"invalid YAML frontmatter: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, "frontmatter must be a mapping (key: value)"
    return data, None


def _parse_yaml_minimal(text: str) -> tuple[dict[str, Any], str | None]:
    """Tiny YAML subset: top-level `key: value` lines, plus `|`/`>` blocks.

    This is intentionally narrow — agent/skill frontmatter in practice is
    a flat mapping of strings. If users have nested structures, install
    PyYAML.
    """
    out: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line.startswith(" ") or line.startswith("\t"):
            # Indented continuation outside a known block — treat as warning
            # but don't fail the whole parse.
            i += 1
            continue
        if ":" not in line:
            return {}, f"cannot parse frontmatter line: {raw_line!r}"
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest in ("|", ">"):
            # Block scalar: take subsequent indented lines.
            block: list[str] = []
            j = i + 1
            while j < len(lines):
                bl = lines[j]
                if bl.strip() == "":
                    block.append("")
                    j += 1
                    continue
                if bl.startswith(" ") or bl.startswith("\t"):
                    # Strip the common leading indent (2 spaces is typical).
                    block.append(bl.lstrip())
                    j += 1
                    continue
                break
            joiner = "\n" if rest == "|" else " "
            out[key] = joiner.join(block).strip()
            i = j
            continue
        # Strip surrounding quotes if present.
        if (rest.startswith('"') and rest.endswith('"') and len(rest) >= 2) or (
            rest.startswith("'") and rest.endswith("'") and len(rest) >= 2
        ):
            rest = rest[1:-1]
        out[key] = rest
        i += 1
    return out, None
