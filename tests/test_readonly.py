"""Hard guarantee: the auditor never writes to the target directory.

Brief section 3 + acceptance criterion in section 6: the tool is strictly
read-only. We verify this by snapshotting every (path, mtime, size) under
the fixture before and after a full audit run.
"""

import os
from pathlib import Path

from claude_config_auditor.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot(root: Path) -> dict[str, tuple[float, int]]:
    snap: dict[str, tuple[float, int]] = {}
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            st = p.stat()
            snap[str(p.relative_to(root))] = (st.st_mtime, st.st_size)
    return snap


def test_auditor_does_not_modify_target(capsys):
    target = FIXTURES / "good"
    before = _snapshot(target)
    rc = main([str(target), "--no-color"])
    capsys.readouterr()
    assert rc == 0
    after = _snapshot(target)
    assert before == after, "auditor modified files in the target directory"


def test_auditor_does_not_modify_broken_fixture(capsys):
    target = FIXTURES / "broken"
    before = _snapshot(target)
    rc = main([str(target), "--no-color"])
    capsys.readouterr()
    assert rc == 0
    after = _snapshot(target)
    assert before == after
