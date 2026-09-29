"""Admin Mode tool layer: real, bounded actions the owner can trigger from chat.

Every tool is deliberately boring and observable: it runs a local process,
returns a short single-line summary that fits inside the 150-character AQW chat
cap, and carries structured evidence so the router can log *what actually
happened* instead of trusting the model's prose.

Two hard rules hold everywhere:

1. Provider credentials never cross a process boundary. Child processes get an
   allowlisted environment built by :meth:`AgentTools._child_env`.
2. Ambiguous or destructive shell work is refused. Only read-only, allowlisted
   commands run, and only when the owner explicitly opted in.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_AGENT_COMMAND = "hermes"
_WEB_TOOLSETS = "web"
_UPGRADE_TOOLSETS = "web,file,terminal"

# Names that never enter a child environment. The project keeps its provider
# key in SKUA_AI_*; other providers commonly use these suffixes.
_SECRET_PREFIXES = ("SKUA_AI_",)
_SECRET_SUFFIXES = ("_API_KEY", "_APIKEY", "_ACCESS_TOKEN", "_AUTH_TOKEN", "_SECRET", "_PASSWORD")

# Only these verbs may be executed through run_command. Anything else is
# refused rather than guessed at.
_ALLOWED_COMMANDS = frozenset(
    {
        "dir", "ls", "pwd", "cd", "echo", "type", "cat", "where", "which",
        "pytest", "python", "python3", "py", "git", "node", "npm", "rg", "find",
    }
)
# Shell chaining and redirection would make the verb allowlist meaningless.
_SHELL_METACHARS = ("&&", "||", ";", "|", ">", "<", "`", "$(")

_SNAPSHOT_IGNORED_DIRS = frozenset(
    {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv"}
)


def _one_line(text: str, limit: int = 300) -> str:
    """Collapse arbitrary process output into one trimmed line."""
    flat = " ".join((text or "").split())
    return flat[:limit].strip()


def _redacted_names(names: Iterable[str]) -> list[str]:
    return [n for n in names]


def is_allowed_command(command: str) -> bool:
    """True when ``command`` is a single, read-only allowlisted invocation."""
    text = (command or "").strip()
    if not text:
        return False
    if any(token in text for token in _SHELL_METACHARS):
        return False
    verb = text.split(maxsplit=1)[0].strip().lower()
    if verb.endswith(".exe"):
        verb = verb[:-4]
    if verb not in _ALLOWED_COMMANDS:
        return False
    # `pip install` / `npm install` mutate the machine, not the project.
    lowered = text.lower()
    if " install" in lowered or lowered.startswith(("pip", "pip3")):
        return False
    return True


@dataclass
class ToolResult:
    """Outcome of one admin tool call."""

    ok: bool
    summary: str
    detail: str = ""
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.summary = _one_line(self.summary)


class AgentTools:
    """Bounded, evidence-producing actions for Admin Mode."""

    def __init__(
        self,
        project_dir: str | os.PathLike[str],
        *,
        agent_command: str = DEFAULT_AGENT_COMMAND,
        timeout: float = 600.0,
        code_timeout: float = 30.0,
        shell_enabled: bool = False,
        python: str | None = None,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.agent_command = agent_command
        self.timeout = timeout
        self.code_timeout = code_timeout
        self.shell_enabled = shell_enabled
        self.python = python or sys.executable

    # ------------------------------------------------------------------
    # process plumbing
    # ------------------------------------------------------------------
    def _child_env(self) -> dict[str, str]:
        """Environment for child processes: secrets stripped, PATH kept."""
        env: dict[str, str] = {}
        for key, value in os.environ.items():
            upper = key.upper()
            if any(upper.startswith(p) for p in _SECRET_PREFIXES):
                continue
            if any(upper.endswith(s) for s in _SECRET_SUFFIXES):
                continue
            env[key] = value
        return env

    def _run(
        self,
        argv,
        *,
        shell: bool = False,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        """Run one child process inside the project directory."""
        return subprocess.run(
            argv,
            shell=shell,
            cwd=str(self.project_dir),
            env=env or self._child_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self.timeout,
        )

    def _agent(self, prompt: str, toolsets: str) -> subprocess.CompletedProcess:
        argv = [self.agent_command, "-t", toolsets, "-z", prompt]
        return self._run(argv)

    # ------------------------------------------------------------------
    # tools
    # ------------------------------------------------------------------
    def web_search(self, query: str) -> ToolResult:
        """Research an open-web question through the local agent's web toolset."""
        question = (query or "").strip()
        if not question:
            return ToolResult(False, "Perintah cari butuh kata kunci.")
        prompt = (
            f"Cari di web: {question}\n"
            "Jawab singkat dan faktual dalam bahasa Indonesia, maksimal 300 karakter. "
            "Sebutkan domain sumbernya. Jangan menulis URL panjang. "
            "Kalau datanya tidak ada, katakan tidak ditemukan."
        )
        try:
            proc = self._agent(prompt, _WEB_TOOLSETS)
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Pencarian '{question}' timeout.")
        except OSError as exc:
            return ToolResult(False, f"Gagal menjalankan pencarian: {exc}")
        answer = _one_line(proc.stdout, 300)
        if proc.returncode != 0 or not answer:
            reason = _one_line(proc.stderr) or f"exit {proc.returncode}"
            return ToolResult(
                False,
                f"Cari '{question}' gagal: {reason}",
                detail=proc.stderr,
                evidence={"returncode": proc.returncode},
            )
        return ToolResult(
            True,
            answer,
            detail=proc.stdout,
            evidence={"query": question, "returncode": proc.returncode},
        )

    def run_command(self, command: str) -> ToolResult:
        """Run one allowlisted read-only shell command (opt-in)."""
        text = (command or "").strip()
        if not is_allowed_command(text):
            return ToolResult(
                False,
                f"Perintah '{_one_line(text, 60)}' tidak diizinkan.",
                evidence={"reason": "not_allowlisted"},
            )
        if not self.shell_enabled:
            return ToolResult(
                False,
                "Shell dimatikan (SKUA_ADMIN_SHELL=0).",
                evidence={"reason": "shell_disabled"},
            )
        try:
            proc = self._run(text, shell=True, timeout=self.code_timeout)
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Perintah '{text}' timeout.")
        except OSError as exc:
            return ToolResult(False, f"Perintah '{text}' gagal: {exc}")
        output = _one_line(proc.stdout or proc.stderr, 300)
        return ToolResult(
            proc.returncode == 0,
            output or f"'{text}' selesai tanpa output.",
            detail=(proc.stdout or "") + (proc.stderr or ""),
            evidence={"command": text, "returncode": proc.returncode},
        )

    def run_code(self, code: str) -> ToolResult:
        """Execute a short Python snippet inside the project, sandboxed by env."""
        snippet = code or ""
        if not snippet.strip():
            return ToolResult(False, "Kode kosong.")
        try:
            proc = self._run(
                [self.python, "-c", snippet], timeout=self.code_timeout
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "Kode timeout.", evidence={"reason": "timeout"})
        except OSError as exc:
            return ToolResult(False, f"Kode gagal jalan: {exc}")
        if proc.returncode != 0:
            reason = _one_line(proc.stderr or proc.stdout, 300)
            return ToolResult(
                False,
                f"Kode error: {reason}",
                detail=proc.stderr,
                evidence={"returncode": proc.returncode},
            )
        return ToolResult(
            True,
            _one_line(proc.stdout, 300) or "Kode selesai tanpa output.",
            detail=proc.stdout,
            evidence={"returncode": 0},
        )

    def project_upgrade(self, goal: str) -> ToolResult:
        """Plan-free self-upgrade: one bounded agent run, then verify with tests.

        The agent may edit project files, so the whole run is bracketed by a
        fingerprint of the tree: anything it touched is reported as evidence,
        and a failing test suite turns the upgrade into a failure rather than a
        success message.
        """
        objective = (goal or "").strip()
        if not objective:
            return ToolResult(False, "Perintah upgrade butuh tujuan.")
        before = self.snapshot()
        prompt = (
            "Kamu mengerjakan self-upgrade untuk project Python di folder ini:\n"
            f"{self.project_dir}\n\n"
            f"TUJUAN: {objective}\n\n"
            "Aturan wajib:\n"
            "1. Kerjakan hanya di dalam folder project ini.\n"
            "2. Jangan membaca, menulis, atau menampilkan file .env atau kredensial apa pun.\n"
            "3. Jangan menginstal paket global dan jangan mengubah konfigurasi sistem.\n"
            "4. Pertahankan gaya dan konvensi kode yang sudah ada.\n"
            "5. Setelah selesai, jalankan: python -m pytest tests/ -q  (dengan PYTHONPATH=src).\n"
            "6. Laporkan file yang diubah dan hasil test secara jujur. Kalau test gagal, katakan gagal.\n"
        )
        try:
            proc = self._agent(prompt, _UPGRADE_TOOLSETS)
        except subprocess.TimeoutExpired:
            return ToolResult(
                False,
                "Upgrade timeout sebelum selesai.",
                evidence={"reason": "timeout", "changed": []},
            )
        except OSError as exc:
            return ToolResult(False, f"Upgrade gagal dijalankan: {exc}")
        after = self.snapshot()
        changed = sorted(
            path
            for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        )
        tests = self._verify_tests()
        evidence = {
            "goal": objective,
            "agent_returncode": proc.returncode,
            "changed": changed,
            "tests": tests,
        }
        if not tests["passed"]:
            return ToolResult(
                False,
                f"Upgrade belum lolos test: {tests['summary']}",
                detail=_one_line(proc.stdout, 800),
                evidence=evidence,
            )
        if not changed:
            return ToolResult(
                False,
                f"Tidak ada file yang berubah. {tests['summary']}",
                detail=_one_line(proc.stdout, 800),
                evidence=evidence,
            )
        listed = ", ".join(changed[:4])
        if len(changed) > 4:
            listed += f" (+{len(changed) - 4} lagi)"
        return ToolResult(
            True,
            f"Upgrade selesai. Ubah: {listed}. {tests['summary']}",
            detail=_one_line(proc.stdout, 800),
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, str]:
        """Fingerprint the project tree so an upgrade can prove what changed."""
        result: dict[str, str] = {}
        try:
            paths = list(self.project_dir.rglob("*"))
        except OSError:
            return result
        for path in paths:
            try:
                if path.is_dir():
                    continue
                if any(part in _SNAPSHOT_IGNORED_DIRS for part in path.parts):
                    continue
                if path.suffix in {".pyc", ".pyo"}:
                    continue
                # Hash file content, not size+mtime. On Windows a same-size
                # rewrite can preserve the old timestamp during a very fast
                # agent run, making a real edit invisible and the upgrade
                # falsely report "Tidak ada file yang berubah".
                digest = hashlib.sha1(path.read_bytes()).hexdigest()
            except OSError:
                continue
            result[str(path.relative_to(self.project_dir)).replace("\\", "/")] = digest
        return result

    def _verify_tests(self) -> dict:
        """Run the project suite and report the real pass/fail count."""
        env = self._child_env()
        env["PYTHONPATH"] = str(self.project_dir / "src")
        try:
            proc = self._run(
                [self.python, "-m", "pytest", "tests/", "-q"],
                timeout=self.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "summary": "test timeout", "output": ""}
        except OSError as exc:
            return {"passed": False, "summary": f"test gagal jalan: {exc}", "output": ""}
        output = (proc.stdout or "") + (proc.stderr or "")
        match = re.search(r"(\d+) passed", output)
        failures = re.search(r"(\d+) failed", output)
        if proc.returncode == 0 and match:
            summary = f"{match.group(1)} test lulus"
            return {"passed": True, "summary": summary, "output": output}
        if failures:
            summary = f"{failures.group(1)} test gagal"
        else:
            summary = f"test exit {proc.returncode}"
        return {"passed": False, "summary": summary, "output": output}
