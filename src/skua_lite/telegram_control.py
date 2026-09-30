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

    def send_photo(
        self,
        chat_id: int,
        image_bytes: bytes,
        *,
        caption: str = "",
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> Any:
        """Send a photo via multipart/form-data."""
        import io, email.generator, random, string
        boundary = "".join(random.choices(string.ascii_lowercase, k=16))
        body = io.BytesIO()
        # chat_id field
        field = f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
        body.write(field.encode("utf-8"))
        # caption field
        if caption:
            cap_field = f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption[:1024]}\r\n"
            body.write(cap_field.encode("utf-8"))
        # photo field
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"ss.png\"\r\nContent-Type: image/png\r\n\r\n".encode("utf-8"))
        body.write(image_bytes)
        if buttons:
            import json as _json
            kb_field = f"--{boundary}\r\nContent-Disposition: form-data; name=\"reply_markup\"\r\n\r\n{_json.dumps({'inline_keyboard': buttons})}\r\n"
            body.write(kb_field.encode("utf-8"))
        body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        data = body.getvalue()
        request = urllib.request.Request(
            f"{self.base_url}/sendPhoto",
            data=data,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise TelegramNetworkError(f"sendPhoto HTTP {exc.code}: {detail[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramNetworkError(str(exc)) from exc
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise TelegramNetworkError("respons Telegram bukan JSON") from exc
        if not decoded.get("ok"):
            code = int(decoded.get("error_code", 0) or 0)
            desc = str(decoded.get("description") or "sendPhoto gagal")
            raise TelegramNetworkError(f"Telegram API {code}: {desc}")
        return decoded.get("result")

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
    "ss": "__screenshot__",
    "resep": "resep",
    "kenapa": "kenapa",
    "pengaturan": "__settings__",
    "setting": "__settings__",
    "config": "__settings__",
    "gantiserver": "__change_server__",
    "gantiakun": "__change_account__",
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
    if verb in {"pengaturan", "setting", "config"}:
        return "__settings__", ""
    if verb in {"ss", "screenshot", "kondisi"}:
        return "__screenshot__", ""
    if verb == "gantiserver":
        return "__change_server__", arg
    if verb == "gantiakun":
        return "__change_account__", arg
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
            {"text": "Pengaturan", "callback_data": "special|settings|"},
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
        "/ss - screenshot kondisi akun (karakter, map, kelas)\n"
        "/resep <item> - pohon bahan merge dari wiki lokal\n"
        "/kenapa - diagnosa kegagalan terakhir + syarat sebelumnya yang dikerjakan\n"
        "/pengaturan - info akun, server, Telegram owner\n"
        "/gantiserver [nama_server] - ganti server (tanpa arg: daftar server)\n"
        "/gantiakun - petunjuk ganti akun (Hint: simpan dulu lewat terminal)\n"
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

    def _is_multi(self) -> bool:
        return bool(getattr(self.orch, "is_multi", False))

    def _execute(self, action: str, arg: Any) -> str:
        if self._is_multi():
            try:
                results = self.orch.broadcast(action, arg)
            except Exception as exc:
                return _bounded(f"Broadcast {action} gagal: {exc}")
            if not results:
                return "Tidak ada akun aktif."
            return _bounded(self.orch.format_broadcast(results))
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

    def _handle_screenshot(self, chat_id: int) -> None:
        """Fetch a render of the current char from AQ Closet and send as photo."""
        import urllib.request as _ur
        orch = self.orch
        bot = getattr(orch, "bot", None)
        username = ""
        if bot:
            username = getattr(bot, "username", "") or ""
        if not username:
            try:
                store = getattr(orch, "store", None)
                if store:
                    username, _ = store.load()
            except Exception:
                pass

        if not username:
            self.transport.send_message(
                chat_id,
                "Tidak bisa mengambil screenshot: username akun tidak diketahui.",
                buttons=panel_buttons(),
            )
            return

        # AQ Closet public render endpoint (char lookup -> outfit.png render)
        char_url = f"https://aq.fanta.id/api/character?name={urllib.request.quote(username, safe='')}"
        current_map = getattr(bot, "current_map", "N/A") if bot else "N/A"
        state = getattr(bot, "state", "N/A") if bot else "N/A"

        # Gather combat state for caption
        combat = getattr(bot, "combat", None)
        class_name = getattr(combat, "class_name", "?") if combat else "?"
        level = getattr(bot, "level", "?") if bot else "?"

        try:
            # 1. Fetch character outfit data
            with _ur.urlopen(_ur.Request(char_url, headers={"User-Agent": "skua-lite/1.0"}), timeout=10) as resp:
                char_data = json.loads(resp.read().decode("utf-8"))
            outfit = char_data.get("outfit") or {}
            items_map = outfit.get("items") or {}
            hair_data = outfit.get("hair") or {}
            colors = outfit.get("colors") or {}
            gender = "F" if str(outfit.get("gender", "M")).upper().startswith("F") else "M"

            def _fmt(slot: str) -> str:
                it = items_map.get(slot) or {}
                return f"{it.get('name','')!s}|{it.get('file','')!s}|{it.get('link','')!s}"

            def _col(key: str) -> str:
                return str(colors.get(key) or "").replace("#", "")

            params = [
                ("g", gender),
                ("armor", _fmt("armor")),
                ("helm", _fmt("helm")),
                ("cape", _fmt("cape")),
                ("weapon", _fmt("weapon")),
                ("pet", _fmt("pet")),
                ("ground", _fmt("ground")),
                ("hair", f"{hair_data.get('name','')!s}|{hair_data.get('file','')!s}"),
                ("c_hair", _col("hair")),
                ("c_skin", _col("skin")),
                ("c_eye", _col("eye")),
                ("c_base", _col("base")),
                ("c_trim", _col("trim")),
                ("c_accessory", _col("accessory")),
            ]
            qs = urllib.request.urlencode(params)
            render_url = f"https://aq.fanta.id/api/outfit.png?{qs}"

            # 2. Download the rendered PNG
            with _ur.urlopen(_ur.Request(render_url, headers={"User-Agent": "skua-lite/1.0"}), timeout=20) as resp:
                img_bytes = resp.read()
            if len(img_bytes) < 100 or not img_bytes.startswith(b"\x89PNG"):
                raise ValueError("bukan PNG valid")
        except Exception as exc:
            # Fallback: send text summary only
            caption_text = (
                f"=== KONDISI AKUN ===\n"
                f"User      : {username}\n"
                f"Level     : {level}\n"
                f"Kelas     : {class_name}\n"
                f"Map       : {current_map}\n"
                f"Status    : {state}\n"
                f"[Render gagal: {str(exc)[:120]}]"
            )
            self.transport.send_message(chat_id, caption_text, buttons=panel_buttons())
            return

        caption = (
            f"👤 {username}  Lv.{level}\n"
            f"⚔ {class_name}\n"
            f"🗺 {current_map}\n"
            f"ℹ {state}"
        )
        try:
            self.transport.send_photo(chat_id, img_bytes, caption=caption, buttons=panel_buttons())
        except Exception as exc:
            self.transport.send_message(
                chat_id,
                f"Render tersedia tapi gagal kirim foto: {exc}\n{caption}",
                buttons=panel_buttons(),
            )

    def _settings_text(self) -> str:
        orch = self.orch
        server = getattr(orch, "server_name", "N/A")
        bot = getattr(orch, "bot", None)
        account = getattr(bot, "username", "")
        if not account:
            try:
                store = getattr(orch, "store", None)
                if store:
                    account, _ = store.load()
            except Exception:
                account = "(belum ada)"
        map_name = getattr(bot, "current_map", "N/A") if bot else "N/A"
        state = getattr(bot, "state", "N/A") if bot else "N/A"
        return _bounded(
            f"=== PENGATURAN SKUA-LITE ===\n"
            f"Akun Aktif   : {account}\n"
            f"Server       : {server}\n"
            f"Map/Lokasi   : {map_name}\n"
            f"Status Bot   : {state}\n"
            f"Telegram ID  : {self.owner_id}\n\n"
            f"Perintah Pengaturan:\n"
            f"- /gantiserver [nama_server] -> ganti server & reconnect\n"
            f"- /gantiakun -> panduan ganti akun"
        )

    def _handle_change_server(self, arg: str) -> tuple[str, list[list[dict[str, str]]] | None]:
        clean = str(arg or "").strip()
        orch = self.orch
        if clean:
            if hasattr(orch, "switch_server"):
                res = orch.switch_server(clean)
                return _bounded(res), panel_buttons()
            return f"Gagal ganti server ke '{clean}': method switch_server tidak tersedia.", panel_buttons()

        # Tanpa argumen: tampilkan daftar server yang online
        from . import servers
        try:
            srv_list = servers.fetch_server_list()
        except Exception as e:
            return f"Gagal mengambil daftar server: {e}", panel_buttons()

        lines = ["=== DAFTAR SERVER AQW ==="]
        buttons: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for name, s in srv_list.items():
            status = "ONLINE" if s.online else "OFFLINE"
            if s.full:
                status += " (PENUH)"
            if s.upgrade_only:
                status += " (UPG)"
            lines.append(f"- {name}: {status}")
            if s.online and not s.full and not s.upgrade_only:
                row.append({"text": name, "callback_data": f"special|srv|{name}"})
                if len(row) >= 2:
                    buttons.append(row)
                    row = []
        if row:
            buttons.append(row)
        buttons.append([{"text": "« Kembali ke Panel", "callback_data": "special|panel|"}])
        lines.append("\nPilih tombol di bawah atau ketik `/gantiserver <nama>`.")
        return _bounded("\n".join(lines)), buttons

    def _handle_change_account(self, arg: str) -> tuple[str, list[list[dict[str, str]]] | None]:
        orch = self.orch
        accounts_store = getattr(orch, "accounts", None)
        usernames: list[str] = []
        active: str | None = None
        if accounts_store is not None:
            try:
                usernames = accounts_store.list_usernames()
                active = accounts_store.active_username()
            except Exception:
                pass

        if not usernames:
            return (
                "=== GANTI AKUN AQW ===\n"
                "Belum ada akun yang tersimpan di daftar.\n\n"
                "Cara menambah akun:\n"
                "Di terminal (saat bot berjalan), ketik:\n"
                "  .tambahakun <username>,<password>\n\n"
                "Setelah itu, /gantiakun akan menampilkan pilihan akun.",
                panel_buttons(),
            )

        lines = ["=== PILIH AKUN AQW ==="]
        buttons: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for u in usernames:
            label = f"{'✓ ' if u == active else ''}{u}"
            row.append({"text": label, "callback_data": f"special|acc|{u}"})
            if len(row) >= 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([{"text": "« Kembali ke Panel", "callback_data": "special|panel|"}])

        cur = f"\nAkun aktif: {active}" if active else ""
        lines.append(cur)
        lines.append("Pilih akun di bawah untuk langsung ganti dan reconnect.")
        return _bounded("\n".join(lines)), buttons

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
        elif action == "__screenshot__":
            self._handle_screenshot(chat_id)
        elif action == "__settings__":
            self.transport.send_message(
                chat_id, self._settings_text(), buttons=self._settings_buttons()
            )
        elif action == "__change_server__":
            text, buttons = self._handle_change_server(arg)
            self.transport.send_message(chat_id, text, buttons=buttons)
        elif action == "__change_account__":
            text, buttons = self._handle_change_account(arg)
            self.transport.send_message(chat_id, text, buttons=buttons)
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
        if self._is_multi():
            try:
                return _bounded(self.orch.dashboard_text())
            except Exception as exc:
                return _bounded(f"Panel multi belum siap: {exc}")
        from .cli import farm_dashboard_lines

        try:
            return _bounded("\n".join(farm_dashboard_lines(self.orch)))
        except Exception as exc:
            return _bounded(f"Panel belum siap: {exc}")

    def _settings_buttons(self) -> list[list[dict[str, str]]]:
        return [
            [
                {"text": "Ganti Server", "callback_data": "special|changeserver|"},
                {"text": "Info Ganti Akun", "callback_data": "special|changeaccount|"},
            ],
            [
                {"text": "Refresh Pengaturan", "callback_data": "special|settings|"},
                {"text": "« Ke Panel", "callback_data": "special|panel|"},
            ],
        ]

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
            new_buttons = panel_buttons()
        elif kind == "special" and action == "panel":
            text = self._panel_text()
            new_buttons = panel_buttons()
        elif kind == "special" and action == "settings":
            text = self._settings_text()
            new_buttons = self._settings_buttons()
        elif kind == "special" and action == "changeserver":
            text, new_buttons = self._handle_change_server(arg)
        elif kind == "special" and action == "changeaccount":
            text, new_buttons = self._handle_change_account(arg)
        elif kind == "special" and action == "srv":
            # Tombol server langsung dari daftar server
            text, new_buttons = self._handle_change_server(arg)
        elif kind == "special" and action == "acc":
            # Tombol akun: ganti ke akun tersimpan tanpa mengetik password
            orch = self.orch
            if hasattr(orch, "switch_account_by_name"):
                text = _bounded(orch.switch_account_by_name(arg))
            else:
                text = f"Gagal ganti akun: method switch_account_by_name tidak tersedia."
            new_buttons = panel_buttons()
        elif kind == "cmd" and action in set(_ALIASES.values()):
            text = self._execute(action, arg)
            new_buttons = panel_buttons()
        else:
            self.transport.answer_callback_query(callback_id, "Tombol tidak dikenal")
            return
        self.transport.answer_callback_query(callback_id, "OK")
        message_id = int(message.get("message_id", 0) or 0)
        if message_id:
            try:
                self.transport.edit_message_text(
                    chat_id, message_id, text, buttons=new_buttons
                )
                return
            except TelegramError:
                pass
        self.transport.send_message(chat_id, text, buttons=new_buttons)

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
