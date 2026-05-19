"""Tests for the diff renderer used by Phase 2 fix previews."""

from __future__ import annotations

from claude_config_auditor.diff import make_diff, render_diff, summarise_diff


# --- make_diff: core behaviour ---------------------------------------------

def test_make_diff_empty_when_unchanged():
    assert make_diff("file.md", "same\ncontent\n", "same\ncontent\n") == ""


def test_make_diff_shows_added_and_removed_lines():
    diff = make_diff(
        "agent.md",
        "name: code-reviewer\ndescription: short\n",
        "name: code-reviewer\ndescription: rewritten description, more specific\n",
    )
    assert "-description: short" in diff
    assert "+description: rewritten description, more specific" in diff


def test_make_diff_marks_new_file_with_dev_null():
    diff = make_diff("CLAUDE.archive.md", "", "Archived content\n")
    assert "--- /dev/null" in diff
    assert "+++ b/CLAUDE.archive.md" in diff
    assert "+Archived content" in diff


def test_make_diff_marks_removal_with_dev_null():
    diff = make_diff("doomed.md", "going away\n", "")
    assert "--- a/doomed.md" in diff
    assert "+++ /dev/null" in diff
    assert "-going away" in diff


def test_make_diff_context_lines_are_configurable():
    before = "\n".join(f"line {i}" for i in range(20)) + "\n"
    after = before.replace("line 10", "LINE TEN")
    short = make_diff("f.md", before, after, context=1)
    long = make_diff("f.md", before, after, context=5)
    assert short.count("line ") < long.count("line ")


def test_make_diff_handles_no_trailing_newline():
    """splitlines(keepends=True) handles a final line without \n. The
    output still includes the change."""
    diff = make_diff("f.md", "a\nb", "a\nB")
    assert "-b" in diff
    assert "+B" in diff


# --- render_diff: ANSI colouring ------------------------------------------

def test_render_diff_no_color_returns_unchanged_text():
    diff = make_diff("f.md", "a\n", "b\n")
    assert render_diff(diff, use_color=False) == diff


def test_render_diff_returns_empty_for_empty_input():
    assert render_diff("", use_color=True) == ""


def test_render_diff_colours_addition_green_and_removal_red():
    diff = make_diff("f.md", "old\n", "new\n")
    coloured = render_diff(diff, use_color=True)
    # Green for additions
    assert "\033[32m+new" in coloured
    # Red for removals
    assert "\033[31m-old" in coloured


def test_render_diff_colours_hunk_header_cyan():
    diff = make_diff("f.md", "a\nb\nc\n", "a\nX\nc\n")
    coloured = render_diff(diff, use_color=True)
    assert "\033[36m@@" in coloured


def test_render_diff_marks_file_headers_bold():
    diff = make_diff("f.md", "a\n", "b\n")
    coloured = render_diff(diff, use_color=True)
    assert "\033[1m---" in coloured
    assert "\033[1m+++" in coloured


def test_render_diff_resets_after_each_line():
    """Every coloured line must end with the reset sequence so a crash
    or pipe doesn't leave the terminal in a coloured state."""
    diff = make_diff("f.md", "a\n", "b\n")
    coloured = render_diff(diff, use_color=True)
    for line in coloured.splitlines(keepends=True):
        if "\033[" in line:
            assert "\033[0m" in line, line


# --- summarise_diff -------------------------------------------------------

def test_summarise_counts_additions_and_removals_only():
    diff = make_diff(
        "f.md",
        "keep this\nremove this\nremove that\n",
        "keep this\nadd this\nadd that\nadd one more\n",
    )
    adds, rems = summarise_diff(diff)
    assert adds == 3
    assert rems == 2


def test_summarise_ignores_file_headers():
    diff = make_diff("f.md", "", "new\nfile\n")
    adds, rems = summarise_diff(diff)
    # +++ and --- lines must NOT count as additions/removals.
    assert adds == 2
    assert rems == 0


def test_summarise_empty_input_is_zero():
    assert summarise_diff("") == (0, 0)
