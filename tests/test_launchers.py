"""Cross-platform one-click launchers for Windows, Linux, and macOS."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_linux_launcher_bootstraps_venv_and_forwards_arguments():
    text = (ROOT / "JALANKAN_SKUA_LITE.sh").read_text(encoding="utf-8")

    assert '#!/usr/bin/env bash' in text
    assert 'python3' in text
    assert 'python -m venv' in text or '"$PYTHON_BIN" -m venv' in text
    assert 'pip install' in text
    assert 'python -m skua_lite' in text or '-m skua_lite' in text
    assert '"$@"' in text


def test_macos_command_launcher_delegates_to_shared_unix_launcher():
    text = (ROOT / "JALANKAN_SKUA_LITE.command").read_text(encoding="utf-8")

    assert '#!/usr/bin/env bash' in text
    assert 'JALANKAN_SKUA_LITE.sh' in text
    assert '"$@"' in text


def test_unix_launchers_have_valid_bash_syntax():
    if os.name == "nt":
        # This Windows runner exposes WSL's bash shim but has no WSL distro.
        # Linux/macOS CI executes the real syntax check below.
        return
    for name in ("JALANKAN_SKUA_LITE.sh", "JALANKAN_SKUA_LITE.command"):
        result = subprocess.run(
            ["bash", "-n", str(ROOT / name)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_unix_launchers_are_executable():
    if os.name == "nt":
        # Git records this bit for macOS/Linux; Windows cannot represent it in
        # NTFS mode bits reliably, so the index is verified separately in CI.
        return
    for name in ("JALANKAN_SKUA_LITE.sh", "JALANKAN_SKUA_LITE.command"):
        assert os.access(ROOT / name, os.X_OK)
