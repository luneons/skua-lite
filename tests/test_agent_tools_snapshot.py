from __future__ import annotations

import os
from pathlib import Path

from skua_lite.agent_tools import AgentTools


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_project_upgrade_detects_same_size_change_with_preserved_mtime(
    tmp_path: Path, monkeypatch
):
    """Snapshot evidence must use bytes, not coarse Windows timestamps."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    target = tmp_path / "src" / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    before_stat = target.stat()

    tools = AgentTools(tmp_path)

    def fake_run(argv, **kwargs):
        if argv[0] == tools.agent_command:
            target.write_text("x = 2\n", encoding="utf-8")  # same byte count
            os.utime(
                target,
                ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns),
            )
            return _Proc(0, "selesai")
        return _Proc(0, "12 passed")

    monkeypatch.setattr(tools, "_run", fake_run)

    result = tools.project_upgrade("ubah nilai")

    assert result.ok is True
    assert result.evidence["changed"] == ["src/mod.py"]
