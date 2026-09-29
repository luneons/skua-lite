"""Unit tests for the Admin Mode tool layer (no network, no long subprocess)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skua_lite.agent_tools import AgentTools, ToolResult, is_allowed_command


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _tools(tmp_path: Path, **kwargs) -> AgentTools:
    return AgentTools(tmp_path, **kwargs)


# --------------------------------------------------------------------------
# child environment: secrets must not leak into tool subprocesses
# --------------------------------------------------------------------------
def test_child_env_drops_provider_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SKUA_AI_API_KEY", "super-secret")
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = _tools(tmp_path)._child_env()

    assert "SKUA_AI_API_KEY" not in env
    assert "SKUA_AI_BASE_URL" not in env
    assert env.get("PATH") == "/usr/bin"


# --------------------------------------------------------------------------
# shell allowlist
# --------------------------------------------------------------------------
def test_shell_allowlist_permits_read_only_and_blocks_destructive():
    assert is_allowed_command("git status") is True
    assert is_allowed_command("dir") is True
    assert is_allowed_command("python -c \"print(1)\"") is True
    assert is_allowed_command("rm -rf /") is False
    assert is_allowed_command("pip install requests") is False
    assert is_allowed_command("del /f /s *") is False
    assert is_allowed_command("") is False


def test_run_command_refuses_command_outside_allowlist(tmp_path):
    tools = _tools(tmp_path, shell_enabled=True)
    result = tools.run_command("rm -rf .")
    assert result.ok is False
    assert "tidak diizinkan" in result.summary.lower()


def test_run_command_disabled_by_default_does_not_execute(tmp_path, monkeypatch):
    called = []
    tools = _tools(tmp_path)
    monkeypatch.setattr(tools, "_run", lambda *a, **k: called.append(a) or _Proc())
    result = tools.run_command("dir")
    assert result.ok is False
    assert called == []


def test_run_command_executes_allowlisted_when_enabled(tmp_path, monkeypatch):
    tools = _tools(tmp_path, shell_enabled=True)
    monkeypatch.setattr(
        tools, "_run", lambda argv, **k: _Proc(0, "total 3\nsrc\n")
    )
    result = tools.run_command("dir")
    assert result.ok is True
    assert "src" in result.summary


# --------------------------------------------------------------------------
# web search via the local agent CLI
# --------------------------------------------------------------------------
def test_web_search_invokes_agent_cli_with_web_toolset(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _Proc(0, "AQW versi .261 rilis 25 September 2026\n")

    tools = _tools(tmp_path)
    monkeypatch.setattr(tools, "_run", fake_run)

    result = tools.web_search("versi terbaru AQW")

    assert result.ok is True
    assert "261" in result.summary
    argv = seen["argv"]
    assert argv[0] == tools.agent_command
    assert "-z" in argv
    assert "web" in argv[argv.index("-t") + 1]
    assert "versi terbaru AQW" in argv[-1]


def test_web_search_empty_query_is_rejected(tmp_path):
    assert _tools(tmp_path).web_search("   ").ok is False


def test_web_search_reports_failure_without_raising(tmp_path, monkeypatch):
    tools = _tools(tmp_path)
    monkeypatch.setattr(tools, "_run", lambda *a, **k: _Proc(1, "", "boom"))
    result = tools.web_search("apa saja")
    assert result.ok is False
    assert "boom" in (result.detail or result.summary)


# --------------------------------------------------------------------------
# project upgrade: plan-run-verify with real evidence
# --------------------------------------------------------------------------
def test_project_upgrade_requires_a_goal(tmp_path):
    assert _tools(tmp_path).project_upgrade("").ok is False


def test_project_upgrade_runs_agent_then_verifies_with_pytest(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    target = tmp_path / "src" / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    tools = _tools(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == tools.agent_command:
            # The agent "writes" code: change the file on disk.
            target.write_text("x = 2\n", encoding="utf-8")
            return _Proc(0, "selesai: mod.py diubah")
        return _Proc(0, "12 passed")

    monkeypatch.setattr(tools, "_run", fake_run)

    result = tools.project_upgrade("tambah fitur x")

    assert result.ok is True
    assert "src/mod.py" in result.summary or "mod.py" in result.summary
    assert result.evidence["tests"]["passed"] is True
    assert result.evidence["changed"] == ["src/mod.py"]
    assert any(tools.agent_command == argv[0] for argv, _ in calls)


def test_project_upgrade_fails_when_tests_do_not_pass(tmp_path, monkeypatch):
    tools = _tools(tmp_path)

    def fake_run(argv, **kwargs):
        if argv[0] == tools.agent_command:
            return _Proc(0, "sudah saya kerjakan")
        return _Proc(1, "1 failed, 11 passed")

    monkeypatch.setattr(tools, "_run", fake_run)

    result = tools.project_upgrade("tambah fitur")

    assert result.ok is False
    assert result.evidence["tests"]["passed"] is False
    assert "test" in result.summary.lower()


def test_project_upgrade_prompt_forbids_secret_and_global_changes(tmp_path, monkeypatch):
    tools = _tools(tmp_path)
    prompts = []

    def fake_run(argv, **kwargs):
        prompts.append(argv[-1])
        return _Proc(0, "ok")

    monkeypatch.setattr(tools, "_run", fake_run)
    tools.project_upgrade("rapikan struktur")

    prompt = prompts[0]
    assert "rapikan struktur" in prompt
    assert ".env" in prompt
    assert "pytest" in prompt


# --------------------------------------------------------------------------
# code runner: real subprocess, hermetic environment
# --------------------------------------------------------------------------
def test_run_code_executes_python_inside_project(tmp_path):
    tools = _tools(tmp_path)
    result = tools.run_code("print(6 * 7)")
    assert result.ok is True
    assert result.summary.strip() == "42"


def test_run_code_reports_traceback_as_failure(tmp_path):
    tools = _tools(tmp_path)
    result = tools.run_code("raise SystemExit(3)")
    assert result.ok is False


def test_run_code_cannot_see_provider_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("SKUA_AI_API_KEY", "super-secret")
    tools = _tools(tmp_path)
    result = tools.run_code(
        "import os; print('LEAK' if os.getenv('SKUA_AI_API_KEY') else 'CLEAN')"
    )
    assert result.ok is True
    assert "CLEAN" in result.summary
    assert "LEAK" not in result.summary


def test_run_code_timeout_is_reported(tmp_path, monkeypatch):
    tools = _tools(tmp_path, code_timeout=0.2)

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0.2))

    monkeypatch.setattr(tools, "_run", fake_run)
    result = tools.run_code("import time; time.sleep(30)")
    assert result.ok is False
    assert "timeout" in result.summary.lower()


def test_tool_result_summary_is_single_line():
    result = ToolResult(ok=True, summary="baris satu\n\nbaris dua")
    assert "\n" not in result.summary
