"""Admin command layer: the owner's `!` language plus movement actions.

Admin commands are the only chat inputs that may trigger side effects:

* ``!cari <query>``      — open-web research through the local agent CLI.
* ``!dapat <item>``      — item source from the local AQW Wiki SQLite mirror.
* ``!item <nama>`` / ``!quest <id/nama>`` / ``!shop <nama>`` — same local lookup.
* ``!upgrade <tujuan>``  — bounded self-upgrade (agent edits, pytest verifies).
* ``!exec <kode>``       — short Python snippet inside the project.
* ``!run <perintah>``    — allowlisted read-only shell (opt-in only).
* ``!join <map>``        — move the game character to another map.
* ``!move <x> <y>``      — walk the character to coordinates.
* ``!status`` / ``!bantuan`` / ``!help`` — bot state / command list.
* ``!admin off``         — leave Admin Mode.

Everything an admin tool reports is evidence, not prose: the router logs the
real return code and the real changed-file list, so a hallucinated "berhasil"
from the model can never masquerade as a verified outcome.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Callable

from .agent_tools import AgentTools, ToolResult
from .wiki_knowledge import WikiKnowledge

# `!cari info dragon fable` -> ("cari", "info dragon fable")
_ADMIN_RE = re.compile(r"^\s*!\s*([A-Za-z]+)\s*(.*)$")
_PRIVATE_TAIL_RE = re.compile(r"(?i)\s+(?:-+|\s*)private\s*$")


def split_private_flag(text: str) -> tuple[str, bool]:
    """Return ``(cleaned, private)`` for a trailing room-scope flag.

    Only an explicit trailing marker counts: ``yulgar`` and ``yulgar-14045``
    stay public, while ``yulgar -private`` selects the private ``-100000``
    room. The helper never treats an embedded room number as private, because
    plain ``<map>-<room>`` joins are valid public joins in AQW.
    """
    cleaned = " ".join(str(text or "").split())
    lowered = cleaned.casefold()
    if lowered in {"-private", "--private", "private"}:
        return "", True
    match = _PRIVATE_TAIL_RE.search(cleaned)
    if match is None:
        return cleaned, False
    return cleaned[: match.start()].strip(), True


def resolve_room_target(map_name: str, *, private: bool) -> str:
    """Resolve an explicit private request to AQW's standard room 100000."""
    target = str(map_name or "").strip()
    if not target or not private:
        return target
    if re.fullmatch(r".+-\d{1,6}", target):
        return target
    return f"{target}-100000"


_COMMANDS = (
    "cari", "dapat", "item", "quest", "shop", "upgrade", "exec", "run",
    "join", "move", "status", "bantuan", "help", "admin",
)


def parse_admin_command(message: str) -> tuple[str, str] | None:
    """Parse an admin command; return None when the message is not one."""
    match = _ADMIN_RE.match(message or "")
    if not match:
        return None
    verb = match.group(1).lower()
    if verb not in _COMMANDS:
        return None
    return verb, match.group(2).strip()


@dataclass
class AdminOutcome:
    """Router-facing result of one parsed admin command."""

    consumed: bool
    reply: str = ""
    admin_off: bool = False


@dataclass
class AdminActions:
    """Game-side side effects, injected so unit tests stay offline."""

    join_map: Callable[[str], bool] = lambda _target: False
    move: Callable[[int, int], bool] = lambda _x, _y: False
    describe_status: Callable[[], str] = lambda: "bot berjalan"


@dataclass
class AdminCommandHandler:
    """Own the `!` command dispatch for one bot session."""

    tools: AgentTools
    actions: AdminActions = field(default_factory=AdminActions)
    on_log: Callable[[str], None] = lambda _message: None
    pending_upgrade: str | None = None
    wiki: WikiKnowledge | None = None

    HELP_TEXT = (
        "admin: !cari <q> !dapat <item> !quest <id/nama> !shop <nama> "
        "!upgrade <tujuan> !join <map> !move <x> <y> "
        "!exec <kode> !run <cmd> !status !admin off"
    )

    def handle(self, sender: str, body: str) -> AdminOutcome:
        """Dispatch one admin line; returns the router-facing outcome."""
        parsed = parse_admin_command(body)
        if parsed is None:
            return AdminOutcome(False)
        verb, arg = parsed

        if verb == "cari":
            return AdminOutcome(True, self._blocking(self.tools.web_search, arg, arg))
        if verb in ("dapat", "item", "quest", "shop"):
            return AdminOutcome(True, self._wiki_lookup(arg))
        if verb == "upgrade":
            return AdminOutcome(True, self._upgrade(arg))
        if verb == "exec":
            return AdminOutcome(True, self._blocking(self.tools.run_code, arg, arg))
        if verb == "run":
            return AdminOutcome(True, self._blocking(self.tools.run_command, arg, arg))
        if verb == "join":
            return AdminOutcome(True, self._game_join(arg))
        if verb == "move":
            return AdminOutcome(True, self._game_move(arg))
        if verb == "status":
            return AdminOutcome(True, self._clamp(self.actions.describe_status()))
        if verb == "admin":
            if arg.lower() in ("off", "mati", "nonaktif"):
                return AdminOutcome(True, "Admin mode off.", admin_off=True)
            return AdminOutcome(True, self.HELP_TEXT)
        return AdminOutcome(True, self.HELP_TEXT)

    # -- long-running tools ------------------------------------------------
    def _wiki_lookup(self, query: str) -> str:
        """Answer from the local Wiki DB (<10ms); never touches the network."""
        text = (query or "").strip()
        if not text:
            return "Format: !dapat <nama item>, misal !dapat Burning Blade"
        try:
            hit = self.wiki.lookup_item(text) if self.wiki is not None else None
        except Exception as exc:  # noqa: BLE001 - a tool must never crash chat
            self.on_log(f"[ADMIN] wiki error: {exc}")
            return "Database wiki belum siap."
        if hit is None:
            return "Item tidak ketemu di wiki lokal. Coba !cari <nama item>."
        return self._clamp(hit.short_answer(150))

    def _blocking(self, call, display: str, arg: str) -> str:
        """Run a tool synchronously and convert the evidence into a reply."""
        try:
            result: ToolResult = call(arg)
        except Exception as exc:  # noqa: BLE001 - a tool must never crash chat
            self.on_log(f"[ADMIN] {display} error: {exc}")
            return "Perintah gagal dijalankan."
        self.on_log(f"[ADMIN] {display} -> ok={result.ok} {result.summary}")
        return self._clamp(result.summary or "Selesai.")

    def _upgrade(self, goal: str) -> str:
        """Two-step self-upgrade: propose the touched files, await `ok`."""
        text = (goal or "").strip()
        if text.lower() in ("ok", "oke", "ya", "setuju", "lanjut", "gas"):
            if not self.pending_upgrade:
                return "Tidak ada rencana upgrade yang menunggu."
            confirmed = self.pending_upgrade
            self.pending_upgrade = None
            try:
                result = self.tools.project_upgrade(confirmed)
            except Exception as exc:  # noqa: BLE001
                self.on_log(f"[ADMIN] upgrade error: {exc}")
                return "Upgrade gagal dijalankan."
            changed = result.evidence.get("changed", [])
            tests = result.evidence.get("tests", {})
            self.on_log(
                "[ADMIN] upgrade "
                f"ok={result.ok} ubah={changed} test={tests}"
            )
            return self._clamp(result.summary or "Upgrade selesai.")
        if not text:
            return "Format: !upgrade <tujuan>"
        self.pending_upgrade = text
        return self._clamp(
            f"Rencana upgrade: {text}. Balas !upgrade ok untuk eksekusi."
        )

    # -- game movement ------------------------------------------------------
    def _game_join(self, target: str) -> str:
        name, private = split_private_flag(target)
        if not name:
            return "Format: !join <map> [-private], misal !join yulgar-14045"
        resolved = resolve_room_target(name, private=private)
        try:
            moved = self.actions.join_map(resolved)
        except Exception as exc:  # noqa: BLE001
            self.on_log(f"[ADMIN] join gagal: {exc}")
            return f"Gagal join {resolved}."
        scope = " (room private)" if private else ""
        return f"Join ke {resolved}{scope}." if moved else f"Gagal join {resolved}."

    def _game_move(self, arg: str) -> str:
        parts = (arg or "").split()
        try:
            x, y = int(parts[0]), int(parts[1])
        except (IndexError, ValueError):
            return "Format: !move <x> <y>, misal !move 850 302"
        try:
            moved = self.actions.move(x, y)
        except Exception as exc:  # noqa: BLE001
            self.on_log(f"[ADMIN] move gagal: {exc}")
            return "Gagal jalan."
        return f"Jalan ke {x},{y}." if moved else "Gagal jalan."

    @staticmethod
    def _clamp(text: str, limit: int = 150) -> str:
        reply = " ".join((text or "").split()).strip()
        if not reply:
            return "Selesai."
        return reply[:limit].rstrip()


class AdminInbox:
    """Thread-safe handoff so slow owner commands never block the chat loop."""

    def __init__(self, handler: AdminCommandHandler) -> None:
        self._handler = handler
        self._lock = threading.Lock()

    def submit(self, sender: str, body: str, send_chat, *, on_off=None) -> bool:
        """Queue one admin line; returns False when it is not an admin command."""
        if parse_admin_command(body) is None:
            return False

        def _work() -> None:
            outcome = self._handler.handle(sender, body)
            if not outcome.consumed:
                return
            if outcome.admin_off and on_off is not None:
                try:
                    on_off()
                except Exception as exc:  # noqa: BLE001
                    self._handler.on_log(f"[ADMIN] gagal menonaktifkan: {exc}")
            if not outcome.reply:
                return
            try:
                send_chat(outcome.reply)
            except Exception as exc:  # noqa: BLE001
                self._handler.on_log(f"[ADMIN] gagal mengirim balasan: {exc}")

        with self._lock:
            thread = threading.Thread(
                target=_work, name="Mele-Admin-Command", daemon=True
            )
            thread.start()
        return True
