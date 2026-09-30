"""Multi-account farming session coordinator.

One ``Orchestrator`` remains responsible for each independent AQW socket,
relogin watcher, combat engine, and farming runtime. ``MultiOrchestrator`` only
owns their lifecycle and broadcasts the existing farm command surface to every
connected slot; it never duplicates gameplay logic.
"""
from __future__ import annotations

import io
import threading
from collections import OrderedDict
from contextlib import redirect_stdout
from typing import Any, Callable


class MultiOrchestrator:
    """Coordinate multiple farming orchestrators behind one control surface."""

    is_multi = True

    def __init__(
        self,
        *,
        run_command: Callable[[Any, str, Any], Any] | None = None,
        accounts: Any = None,
        server_name: str = "Yorumi",
    ) -> None:
        if run_command is None:
            from .cli import dispatch_farm

            run_command = dispatch_farm
        self._run_command = run_command
        self._slots: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.RLock()
        self.accounts = accounts
        self.server_name = server_name
        self.telegram = None

    # --------------------------------------------------------------- slots

    def add_slot(self, username: str, orch: Any) -> None:
        name = str(username or "").strip()
        if not name:
            raise ValueError("username slot kosong")
        with self._lock:
            old = self._slots.get(name)
            if old is not None and old is not orch:
                try:
                    old.shutdown()
                except Exception:
                    pass
            self._slots[name] = orch

    def remove_slot(self, username: str, *, shutdown: bool = True) -> bool:
        with self._lock:
            key = self._find_key(username)
            if key is None:
                return False
            orch = self._slots.pop(key)
        if shutdown:
            try:
                orch.shutdown()
            except Exception:
                pass
        return True

    def _find_key(self, username: str) -> str | None:
        wanted = str(username or "").strip().casefold()
        for key in self._slots:
            if key.casefold() == wanted:
                return key
        return None

    def get_slot(self, username: str) -> Any | None:
        with self._lock:
            key = self._find_key(username)
            return self._slots.get(key) if key is not None else None

    def list_usernames(self) -> list[str]:
        with self._lock:
            return list(self._slots.keys())

    def slot_count(self) -> int:
        with self._lock:
            return len(self._slots)

    def slots(self) -> list[tuple[str, Any]]:
        with self._lock:
            return list(self._slots.items())

    @property
    def primary(self) -> Any | None:
        pairs = self.slots()
        return pairs[0][1] if pairs else None

    @property
    def bot(self) -> Any | None:
        primary = self.primary
        return getattr(primary, "bot", None) if primary else None

    @property
    def farming(self) -> Any | None:
        primary = self.primary
        return getattr(primary, "farming", None) if primary else None

    # ------------------------------------------------------------ broadcast

    def broadcast(self, action: str, arg: Any) -> dict[str, str]:
        """Run one existing farm command for every connected slot.

        A command failure on one account never prevents delivery to the others.
        Returned text is keyed by username for a concise aggregate Telegram
        reply.
        """
        results: dict[str, str] = {}
        for username, orch in self.slots():
            if getattr(orch, "bot", None) is None or getattr(orch, "farming", None) is None:
                results[username] = "OFFLINE: sesi belum tersambung"
                continue
            stream = io.StringIO()
            try:
                with redirect_stdout(stream):
                    result = self._run_command(orch, action, arg)
                output = stream.getvalue().strip()
                if result == "farm_error":
                    results[username] = output or "GAGAL"
                elif result is None:
                    results[username] = output or "DITOLAK"
                else:
                    results[username] = output or "OK"
            except Exception as exc:
                results[username] = f"GAGAL: {exc}"
        return results

    def format_broadcast(self, results: dict[str, str]) -> str:
        if not results:
            return "Tidak ada akun aktif."
        lines = [f"=== HASIL {len(results)} AKUN ==="]
        for username, message in results.items():
            clean = str(message or "OK").strip().replace("\n", " | ")
            lines.append(f"[{username}] {clean}")
        return "\n".join(lines)

    def status_all(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for username, orch in self.slots():
            bot = getattr(orch, "bot", None)
            runtime = getattr(orch, "farming", None)
            if bot is None:
                results[username] = "OFFLINE"
                continue
            state = getattr(bot, "state", "?")
            state = getattr(state, "value", state)
            current_map = getattr(bot, "current_map", "?")
            detail = runtime.status() if runtime is not None else "runtime tidak siap"
            results[username] = f"{state} | {current_map} | {detail}"
        return results

    def dashboard_text(self) -> str:
        return self.format_broadcast(self.status_all()).replace("HASIL", "MULTI-BOT")

    # -------------------------------------------------------------- settings

    def switch_server(self, server_name: str) -> str:
        """Change every active slot to the same server."""
        name = str(server_name or "").strip()
        if not name:
            return "Nama server tidak boleh kosong."
        results: dict[str, str] = {}
        for username, orch in self.slots():
            try:
                results[username] = str(orch.switch_server(name))
            except Exception as exc:
                results[username] = f"GAGAL: {exc}"
        if results and all("berhasil" in text.casefold() for text in results.values()):
            self.server_name = name
        return self.format_broadcast(results)

    def switch_account_by_name(self, username: str) -> str:
        """In multi mode accounts are concurrent, not mutually switched."""
        slot = self.get_slot(username)
        if slot is None:
            return f"Akun '{username}' belum login di sesi multi."
        return f"Akun '{username}' sudah aktif. Semua perintah dikirim ke seluruh akun."

    # -------------------------------------------------------------- lifecycle

    def start_telegram_control(self, config: Any = None) -> bool:
        from .telegram_control import (
            TelegramConfig,
            TelegramControl,
            TelegramControlService,
            TelegramTransport,
        )

        cfg = config or TelegramConfig.from_env()
        if not cfg.enabled or not self.slots():
            return False
        if self.telegram is not None:
            self.telegram.stop()
        service = TelegramControlService(
            TelegramControl(self, TelegramTransport(cfg.token), owner_id=cfg.owner_id),
            on_log=self.log,
        )
        service.start()
        self.telegram = service
        return True

    def log(self, message: str) -> None:
        print(message, flush=True)

    def shutdown(self) -> None:
        if self.telegram is not None:
            try:
                self.telegram.stop()
            except Exception:
                pass
        for _username, orch in self.slots():
            try:
                orch.shutdown()
            except Exception:
                pass
        with self._lock:
            self._slots.clear()
