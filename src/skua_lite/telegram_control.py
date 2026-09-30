"""Owner-only Telegram control panel for the farming runtime.

The token is read from ``SKUA_TELEGRAM_TOKEN``. Telegram user access is locked
by numeric ``SKUA_TELEGRAM_OWNER_ID`` before any farming command is dispatched.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

MAX_MESSAGE_CHARS = 4096
TRUNCATION_MARKER = "\n…[dipotong]"


class TelegramError(RuntimeError):
    """Telegram Bot API failure."""


class TelegramNetworkError(TelegramError):
    """Transient HTTP/network failure."""


class TelegramConflict(TelegramError):
    """HTTP/API 409: another long-poll consumer uses the token."""


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    token: str = ""
    owner_id: int | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        env_file: str | os.PathLike[str] = ".env",
    ) -> "TelegramConfig":
        """Read token + owner from .env file (lower priority) then env overrides."""
        # Load the dotenv file first so process env can override it.
        file_values: dict[str, str] = {}
        path = Path(env_file)
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, sep, val = line.partition("=")
                if sep:
                    file_values[key.strip()] = val.strip().strip("'\"")
        except OSError:
            pass

        # env kwarg takes highest priority; then os.environ; then .env file.
        values = os.environ if env is None else env

        def value(name: str) -> str:
            return str(values.get(name, file_values.get(name, "")) or "").strip()

        token = value("SKUA_TELEGRAM_TOKEN")
        raw_owner = value("SKUA_TELEGRAM_OWNER_ID")
        try:
            owner_id = int(raw_owner) if raw_owner else None
        except ValueError:
            owner_id = None
        return cls(token=token, owner_id=owner_id)


class TelegramTransport:
    """Dependency-free Telegram Bot API JSON transport."""

    def __init__(self, token: str, *, timeout: float = 35.0):
        clean = str(token or "").strip()
        if not clean:
            raise ValueError("token Telegram kosong")
        self.base_url = f"https://api.telegram.org/bot{clean}"
        self.timeout = float(timeout)

    def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            if exc.code == 409:
                raise TelegramConflict(detail or "Telegram HTTP 409") from exc
            raise TelegramNetworkError(
                f"Telegram HTTP {exc.code}: {detail[:300]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramNetworkError(str(exc)) from exc
        try:
            decoded = json.loads(body)
        except (TypeError, ValueError) as exc:
            raise TelegramNetworkError("respons Telegram bukan JSON") from exc
        if not decoded.get("ok"):
            code = int(decoded.get("error_code", 0) or 0)
            description = str(decoded.get("description") or "Telegram API gagal")
            if code == 409:
                raise TelegramConflict(description)
            raise TelegramNetworkError(f"Telegram API {code}: {description}")
        return decoded.get("result")

    def get_me(self) -> dict[str, Any]:
        return dict(self._call("getMe") or {})

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": max(0, int(timeout)),
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = int(offset)
        result = self._call("getUpdates", payload)
        return list(result or [])

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": int(chat_id),
            "text": _bounded(text),
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return self._call("sendMessage", payload)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "text": _bounded(text),
        }
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return self._call("editMessageText", payload)

    def answer_callback_query(self, callback_id: str, text: str = "") -> Any:
        payload: dict[str, Any] = {"callback_query_id": str(callback_id)}
        if text:
            payload["text"] = str(text)[:200]
        return self._call("answerCallbackQuery", payload)


_ALIASES = {
    "st": "status",
    "status": "status",
    "dashboard": "dashboard",
    "join": "join",
    "cell": "cell",
    "cells": "cells",
    "attack": "attack",
    "combat": "combat",
    "level": "level",
    "leveling": "level",
    "auto": "auto",
    "goal": "goal",
    "area": "area",
    "class": "class",
    "weapon": "weapon",
    "armor": "armor",
    "helm": "helm",
    "cape": "cape",
    "item": "item",
    "equip": "equip",
    "chat": "chat",
    "wiki": "wiki",
    "dapat": "dapat",
    "saranfarm": "saranfarm",
}


def parse_telegram_command(text: str) -> tuple[str, Any]:
    """Parse a closed Telegram command set; unknown input never dispatches."""
    raw = str(text or "").strip()
    if not raw:
        return "", ""
    first, _, rest = raw.partition(" ")
    verb = first.lstrip("./").split("@", 1)[0].casefold()
    arg = rest.strip()
    if verb in {"start", "help", "bantuan"}:
        return "__help__", ""
    if verb in {"panel", "menu"}:
        return "__panel__", ""
    if verb in {"stop", "berhenti"}:
        return "__stop__", ""
    action = _ALIASES.get(verb)
    return (action, arg) if action else ("", "")


def panel_buttons() -> list[list[dict[str, str]]]:
    return [
        [
            {"text": "Dashboard", "callback_data": "cmd|dashboard|"},
            {"text": "Combat", "callback_data": "cmd|combat|"},
        ],
        [
            {"text": "Level 100 Public", "callback_data": "cmd|level|100"},
            {"text": "Level 100 -private", "callback_data": "cmd|level|100 -private"},
        ],
        [
            {"text": "Lawan Semua", "callback_data": "cmd|goal|clear_map"},
            {"text": "STOP", "callback_data": "special|stop|"},
        ],
        [
            {"text": "Refresh", "callback_data": "special|panel|"},
        ],
    ]


def help_text() -> str:
    return (
        "SKUA-LITE TELEGRAM CONTROL\n"
        "Owner-only berdasarkan numeric Telegram user ID.\n\n"
        "/panel - tombol kontrol\n"
        "/dashboard atau /status\n"
        "/level [target] [-private]\n"
        "/join <map> [-private]\n"
        "/cell <cell> [pad]\n"
        "/attack <monster|auto|off>\n"
        "/goal <clear_map|stop>\n"
        "/auto <tujuan|status|stop>\n"
        "/combat, /area, /cells\n"
        "/class, /weapon, /armor, /helm, /cape\n"
        "/wiki <item|lokasi|quest>\n"
        "/saranfarm <monster>\n"
        "/stop - hentikan leveling, combat, dan auto\n"
    )


def _bounded(text: str) -> str:
    value = str(text or "")
    if len(value) <= MAX_MESSAGE_CHARS:
        return value
    return value[: MAX_MESSAGE_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


class TelegramControl:
    """Owner-gated Telegram update router for one Orchestrator."""

    def __init__(
        self,
        orch: Any,
        transport: TelegramTransport,
        *,
        owner_id: int | None,
        run_command: Callable[[Any, str, Any], Any] | None = None,
    ):
        self.orch = orch
        self.transport = transport
        self.owner_id = int(owner_id) if owner_id is not None else None
        if run_command is None:
            from .cli import dispatch_farm

            run_command = dispatch_farm
        self.run_command = run_command

    def _authorize(self, user_id: int, chat_id: int, *, callback_id: str = "") -> bool:
        if self.owner_id is None:
            text = (
                "Telegram owner belum dikunci. Tambahkan ke .env:\n"
                f"SKUA_TELEGRAM_OWNER_ID={int(user_id)}\n"
                "Lalu restart skua-lite."
            )
            if callback_id:
                self.transport.answer_callback_query(callback_id, "Owner belum dikonfigurasi")
            else:
                self.transport.send_message(chat_id, text)
            return False
        if int(user_id) != self.owner_id:
            if callback_id:
                self.transport.answer_callback_query(callback_id, "Ditolak: bukan owner")
            else:
                self.transport.send_message(chat_id, "Ditolak: akun Telegram ini bukan owner.")
            return False
        return True

    def _execute(self, action: str, arg: Any) -> str:
        stream = io.StringIO()
        with redirect_stdout(stream):
            result = self.run_command(self.orch, action, arg)
        output = stream.getvalue().strip()
        if result == "farm_error":
            return _bounded(output or f"Perintah {action} gagal.")
        if result is None:
            return _bounded(output or f"Perintah {action} ditolak.")
        return _bounded(output or f"OK: {action} {str(arg).strip()}".strip())

    def _execute_stop(self) -> str:
        outputs: list[str] = []
        for action, arg in (("level", "stop"), ("attack", "off"), ("auto", "stop")):
            text = self._execute(action, arg)
            if text:
                outputs.append(text)
        return _bounded("\n".join(outputs) or "Semua aktivitas dihentikan.")

    def handle_message(self, message: Mapping[str, Any]) -> None:
        sender = message.get("from") or {}
        chat = message.get("chat") or {}
        user_id = int(sender.get("id", 0) or 0)
        chat_id = int(chat.get("id", 0) or 0)
        if not user_id or not chat_id:
            return
        if not self._authorize(user_id, chat_id):
            return
        action, arg = parse_telegram_command(str(message.get("text") or ""))
        if action == "__help__":
            self.transport.send_message(chat_id, help_text(), buttons=panel_buttons())
        elif action == "__panel__":
            self.transport.send_message(
                chat_id, self._panel_text(), buttons=panel_buttons()
            )
        elif action == "__stop__":
            self.transport.send_message(chat_id, self._execute_stop(), buttons=panel_buttons())
        elif action:
            self.transport.send_message(
                chat_id, self._execute(action, arg), buttons=panel_buttons()
            )
        else:
            self.transport.send_message(
                chat_id, "Perintah tidak dikenal. Gunakan /help atau /panel.",
                buttons=panel_buttons(),
            )

    def _panel_text(self) -> str:
        from .cli import farm_dashboard_lines

        try:
            return _bounded("\n".join(farm_dashboard_lines(self.orch)))
        except Exception as exc:
            return _bounded(f"Panel belum siap: {exc}")

    def handle_callback(self, callback: Mapping[str, Any]) -> None:
        sender = callback.get("from") or {}
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        user_id = int(sender.get("id", 0) or 0)
        chat_id = int(chat.get("id", 0) or 0)
        callback_id = str(callback.get("id") or "")
        if not user_id or not chat_id:
            return
        if not self._authorize(user_id, chat_id, callback_id=callback_id):
            return
        pieces = str(callback.get("data") or "").split("|", 2)
        if len(pieces) != 3:
            self.transport.answer_callback_query(callback_id, "Tombol tidak valid")
            return
        kind, action, arg = pieces
        if kind == "special" and action == "stop":
            text = self._execute_stop()
        elif kind == "special" and action == "panel":
            text = self._panel_text()
        elif kind == "cmd" and action in set(_ALIASES.values()):
            text = self._execute(action, arg)
        else:
            self.transport.answer_callback_query(callback_id, "Tombol tidak dikenal")
            return
        self.transport.answer_callback_query(callback_id, "OK")
        message_id = int(message.get("message_id", 0) or 0)
        if message_id:
            try:
                self.transport.edit_message_text(
                    chat_id, message_id, text, buttons=panel_buttons()
                )
                return
            except TelegramError:
                pass
        self.transport.send_message(chat_id, text, buttons=panel_buttons())

    def poll_once(self, offset: int | None) -> int | None:
        updates = self.transport.get_updates(offset=offset, timeout=25)
        next_offset = offset
        for update in updates:
            update_id = int(update.get("update_id", 0) or 0)
            next_offset = max(next_offset or 0, update_id + 1)
            if isinstance(update.get("message"), dict):
                self.handle_message(update["message"])
            elif isinstance(update.get("callback_query"), dict):
                self.handle_callback(update["callback_query"])
        return next_offset

    def serve(
        self,
        *,
        stop_event: threading.Event | Any,
        on_log: Callable[[str], None] | None = None,
        conflict_limit: int = 3,
    ) -> None:
        log = on_log or (lambda _message: None)
        offset: int | None = None
        conflicts = 0
        while not stop_event.is_set():
            try:
                offset = self.poll_once(offset)
                conflicts = 0
            except TelegramConflict as exc:
                conflicts += 1
                log(f"[TELEGRAM] konflik 409 ({conflicts}/{conflict_limit}): {exc}")
                if conflicts >= conflict_limit:
                    log("[TELEGRAM] polling dihentikan: ada instance lain memakai token.")
                    return
                if stop_event.wait(1.0):
                    return
            except TelegramNetworkError as exc:
                log(f"[TELEGRAM] polling gagal: {exc}")
                if stop_event.wait(1.0):
                    return
            except Exception as exc:
                log(f"[TELEGRAM] handler error: {exc}")
                if stop_event.wait(1.0):
                    return


class TelegramControlService:
    """Lifecycle wrapper owned by Orchestrator."""

    def __init__(self, control: TelegramControl, *, on_log: Callable[[str], None]):
        self.control = control
        self.on_log = on_log
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def check(self) -> dict[str, Any]:
        return self.control.transport.get_me()

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        me = self.check()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.control.serve,
            kwargs={"stop_event": self.stop_event, "on_log": self.on_log},
            name="TelegramControl",
            daemon=True,
        )
        self.thread.start()
        username = str(me.get("username") or me.get("first_name") or "bot")
        self.on_log(f"[TELEGRAM] control aktif: @{username}")

    def stop(self) -> None:
        self.stop_event.set()
        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
