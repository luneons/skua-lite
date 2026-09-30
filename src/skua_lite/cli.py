"""Antarmuka menu interaktif untuk skua-lite.

Menu yang diminta pengguna:
  MENU -> CHAT : kirim pesan teks ke room / zone
  MENU -> ACTION:
      - reload   : join ulang map saat ini & re-AFK
      - logout   : disconnect dari server
      - minimize : sembunyikan window terminal (jalan di latar belakang)
  MENU -> STATUS: tampilkan status bot (map, room, state, afk)
  MENU -> QUIT  : hentikan bot dan keluar
"""
from __future__ import annotations

import ctypes
import os
import platform
import sys
import time
from typing import Any

from .auto_planner import AutoGoalParser
from .admin_commands import split_private_flag


SW_HIDE = 0
SW_MINIMIZE = 6
SW_SHOW = 5


def minimize_console(hide_completely: bool = False) -> bool:
    """Minimize atau sembunyikan window console di Windows."""
    if platform.system() != "Windows":
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        user32 = ctypes.WinDLL("user32")
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return False
        cmd = SW_HIDE if hide_completely else SW_MINIMIZE
        user32.ShowWindow(hwnd, cmd)
        return True
    except Exception:
        return False


def parse_command(raw: str) -> tuple[str, str]:
    """Parse input pengguna menjadi tuple (action, argument)."""
    text = raw.strip()
    if not text:
        return "noop", ""

    # Shortcut angka
    num_map = {
        "1": ("menu", "chat"),
        "2": ("menu", "action"),
        "3": ("menu", "status"),
        "0": ("menu", "quit"),
    }
    if text in num_map:
        return num_map[text]

    parts = text.split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb in ("chat", "c", "say"):
        return "chat", arg
    if verb in ("action", "act", "a"):
        return "action", arg.lower()
    if verb in ("reload", "r"):
        return "action", "reload"
    if verb in ("logout", "disconnect"):
        return "action", "logout"
    if verb in ("minimize", "min", "bg", "background"):
        return "action", "minimize"
    if verb == "hide":
        return "action", "hide"
    if verb == "log":
        return "action", f"log {arg}".strip()
    if verb == "cls" or verb == "clear":
        return "clear", ""
    if verb in ("status", "st", "info"):
        return "status", ""
    if verb in ("debug", "diag", "presence"):
        return "debug", ""
    if verb in ("quit", "exit", "q"):
        return "quit", ""
    if verb in ("help", "h", "?"):
        return "help", ""

    return "unknown", text


def dispatch(bot: Any, action: str, arg: str) -> str | None:
    """Eksekusi aksi terhadap bot. Mengembalikan flag khusus ('minimize', 'quit', dll)."""
    if action == "chat":
        if not arg:
            print("[INFO] format: chat <pesan>")
            return None
        bot.chat(arg)
        return "chat_sent"

    if action == "clear":
        os.system("cls" if platform.system() == "Windows" else "clear")
        print_banner(bot)
        return "cleared"

    if action == "action":
        sub = arg.lower()
        if sub in ("log", "log on", "log off"):
            print("[ACTION] packet debug log diminta (butuh orchestrator)")
            return "log_toggled"
        if sub in ("reload", "r"):
            bot.reload()
            return "reloaded"
        if sub in ("logout", "disc", "disconnect"):
            bot.logout()
            return "logged_out"
        if sub in ("minimize", "min", "bg", "hide"):
            hide = "hide" in sub
            ok = minimize_console(hide_completely=hide)
            print(f"[ACTION] console {'disembunyikan' if hide else 'diminimize'} (Win32: {ok}). Bot tetap berjalan di latar belakang.")
            return "minimize"
        print(f"[WARN] aksi '{arg}' tidak dikenal. Pilihan: reload, logout, minimize, hide, log on/off")
        return None

    if action == "status":
        print(
            f"[STATUS] State: {bot.state.value} | Map: {bot.current_map} "
            f"| Room ID: {bot.room_id} | AFK: {bot.is_afk}"
        )
        return "status"

    if action == "debug":
        orchestrator = getattr(bot, "orchestrator", None)
        if orchestrator is None:
            print("[DEBUG] diagnostik tidak tersedia.")
            return None
        orchestrator.dump_presence()
        path = orchestrator.dump_last_packet_to_file()
        if path:
            print(f"[DEBUG] paket terakhir disimpan: {path}")
        return "debug"

    return None


def _farm_scope(current_map: str) -> str:
    """Room scope dari nama map penuh; hanya akhiran -100000 yang private."""
    return "PRIVATE" if str(current_map or "").casefold().endswith("-100000") else "PUBLIC"


def _farm_location(orch: Any) -> str:
    bot = getattr(orch, "bot", None)
    current = str(getattr(bot, "current_map", "") or "-")
    base = current.split("-")[0] if "-" in current else current
    cell = getattr(getattr(getattr(orch, "farming", None), "combat", None), "state", None)
    cell_name = str(getattr(cell, "cell", "") or "-")
    return f"{base} / {cell_name}"


def _farm_character(orch: Any) -> str:
    bot = getattr(orch, "bot", None)
    level = getattr(bot, "level", "?")
    state = getattr(getattr(getattr(orch, "farming", None), "combat", None), "state", None)
    class_name = str(getattr(state, "class_name", "") or "-")
    return f"Level {level} {class_name}".strip()


def _farm_task(orch: Any) -> str:
    runtime = getattr(orch, "farming", None)
    planner = getattr(runtime, "auto_planner", None) if runtime is not None else None
    goal = getattr(planner, "current_goal", None)
    parts: list[str] = []
    leveling_target = getattr(runtime, "_leveling_target", 0) or 0
    if leveling_target:
        try:
            leveling_active = bool(runtime.is_leveling())
        except Exception:
            leveling_active = True
        if leveling_active:
            bot = getattr(orch, "bot", None)
            current = getattr(bot, "level", "?")
            parts.append(f"LEVELING {current} -> {leveling_target}")
    if planner is not None and bool(getattr(planner, "active", False)) and goal is not None:
        scope = "private" if bool(getattr(goal, "private", False)) else "public"
        parts.append(f"AUTO {str(getattr(goal, 'kind', '')).upper()} {goal.target_name} ({scope})")
    engine = getattr(runtime, "combat", None) if runtime is not None else None
    combat_on = bool(getattr(engine, "running", False))
    target = str(getattr(engine, "target_name", "") or "").strip()
    if combat_on:
        parts.append(f"COMBAT ON -> {target or 'semua di cell'}")
    if not parts:
        return "IDLE"
    return " + ".join(parts)


def _farm_state(orch: Any) -> str:
    runtime = getattr(orch, "farming", None)
    engine = getattr(runtime, "combat", None) if runtime is not None else None
    if bool(getattr(engine, "running", False)):
        return "COMBAT"
    planner = getattr(runtime, "auto_planner", None) if runtime is not None else None
    if planner is not None and bool(getattr(planner, "active", False)):
        return "AUTO"
    try:
        leveling_active = bool(runtime.is_leveling())
    except Exception:
        leveling_active = False
    if bool(getattr(runtime, "_leveling_target", 0)) and leveling_active:
        return "LEVELING"
    return "IDLE"


def farm_dashboard_lines(orch: Any) -> list[str]:
    """Satu layar status farming: lokasi, karakter, dan tugas aktif."""
    bot = getattr(orch, "bot", None)
    current = str(getattr(bot, "current_map", "") or "-")
    server = getattr(bot, "server", None)
    server_name = str(getattr(server, "name", "") or "-")
    return [
        "FARMING DASHBOARD",
        f"[{_farm_scope(current)}] {server_name} | {current}",
        f"Lokasi: {_farm_location(orch)}",
        f"Karakter: {_farm_character(orch)}",
        f"Tugas: {_farm_task(orch)}",
    ]


def farm_prompt(orch: Any) -> str:
    """Prompt pendek kontekstual: scope, lokasi, dan status tugas."""
    bot = getattr(orch, "bot", None)
    current = str(getattr(bot, "current_map", "") or "-")
    base = current.split("-")[0] if "-" in current else current
    state = getattr(
        getattr(getattr(getattr(orch, "farming", None), "combat", None), "state", None),
        "cell",
        "",
    )
    cell = str(state or "-")
    return f"[{_farm_scope(current)} | {base}/{cell} | {_farm_state(orch)}] > "


def print_farm_help() -> None:
    """Bantuan farming yang dikelompokkan; tanpa mengubah parser lama."""
    print("MULAI CEPAT")
    print("  .dashboard / .ui            -> status farming + tugas aktif")
    print("  .leveling [level] [-private] -> leveling otomatis")
    print("  .attack <nama> / auto / off -> mulai atau hentikan serangan")
    print("NAVIGASI")
    print("  .join <map> [-private]      -> pindah map")
    print("  .cell <nama> [pad]          -> pindah cell")
    print("  .cells                      -> daftar cell hasil scan")
    print("  .move <x> <y>               -> gerak ke koordinat")
    print("PERTARUNGAN")
    print("  .goal map / stop            -> lawan semua musuh / berhenti")
    print("  .combat                     -> status combat + monster")
    print("  .capture on|off             -> rekam paket combat")
    print("PERLENGKAPAN")
    print("  .class / .weapon / .armor / .helm / .cape")
    print("  .item scan|list|type <tipe> -> daftar item")
    print("  .equip <nomor|nama>         -> pakai item")
    print("  .drop / .rest / .booster / .aggro / .quest / .sell / .bank")
    print("INFO")
    print("  .status / .area / .dapat <item> / .wiki <item|lokasi|quest> / .resep <item>")
    print("  .saranfarm <monster>        -> cari map monster dari wiki")
    print("  .tambahakun <user>,<pass>   -> simpan akun baru (koma agar nama berspasi aman)")
    print("  .editakun <user>,<pass baru>-> ganti password akun tersimpan")
    print("  .hapusakun <user>           -> hapus akun dari daftar")
    print("  .daftarakun                 -> tampilkan semua akun tersimpan")
    print("Tanpa -private = room publik; -private = room 100000.")


def print_farm_banner(orch: Any) -> None:
    bot = orch.bot
    for line in farm_dashboard_lines(orch):
        print(line)
    print(f" User   : {bot.username}")
    print(f" Status : {bot.state.value} | AFK: {bot.is_afk}")
    print(f" AI     : OFF (mode farming tidak memuat AI/Admin)")
    print("-" * 56)
    print(" Ketik .dashboard untuk status, .help untuk semua perintah.")
    print("=" * 56 + "\n")


def _goal_noun(text: str) -> bool:
    words = set(text.replace("-", " ").split())
    return bool(words & {"musuh", "monster", "enemy", "enemies"})


_GOAL_VERBS = {"lawan", "serang", "habisi", "basmi", "bunuh", "clear"}


def _private_requested(text: str) -> tuple[str, bool]:
    """Strip a trailing `-private` flag; public is the default.

    This is a thin CLI alias over the shared admin helper so chat (`!join`)
    and terminal (`.join`/`.leveling`) accept exactly the same room scope.
    """
    return split_private_flag(text)


def _parse_goal_sentence(raw: str) -> tuple[str, str] | None:
    text = " ".join(str(raw or "").strip().lower().rstrip(".!?").split())
    words = set(text.replace("-", " ").split())
    if not text:
        return None
    if ("berhenti" in words or "stop" in words) and _goal_noun(text):
        return "goal", "stop"
    map_scope = (
        "map ini" in text
        or "seluruh map" in text
        or "semap" in words
        or "map" in words
    )
    all_scope = bool(words & {"semua", "seluruh", "all"})
    if words & _GOAL_VERBS and _goal_noun(text) and map_scope and all_scope:
        return "goal", "clear_map"
    return None


def parse_farm_command(raw: str) -> tuple[str, str]:
    """Parse `.aksi <arg>`; natural goal sentences do not need a dot prefix.

    Users give goals in plain sentences ("lawan semua musuh..."), so parse any
    familiar phrasing to the same goal. Legacy `farm <aksi> <arg>` also works.
    """
    text = raw.strip()
    norm = " ".join(text.lower().split())
    goal = _parse_goal_sentence(text)
    if goal is not None:
        return goal
    if norm.rstrip(".!?") in {"berhenti", "berhenti lawan", "stop", "attack off"}:
        return "goal", "stop"
    # Autonomous goals are a closed shape too: `auto cari X x5 dari Y`,
    # `auto farming Y`, `auto selesaikan quest 2260`. A sentence that matches
    # the `auto` prefix but no known goal shape is refused (never guessed).
    if norm.startswith("auto ") or norm in {"auto", ".auto"}:
        goal = AutoGoalParser.parse(text)
        return ("auto", goal) if goal is not None else ("auto", "")
    if text.startswith("."):
        rest = text[1:].strip()
    elif text.lower() == "farm" or text.lower().startswith("farm "):
        rest = text[4:].strip()
    elif " " in norm and norm.split()[0] in _GOAL_VERBS and _goal_noun(norm):
        return "goal", "clear_map"
    else:
        return "", ""
    if not rest:
        return "status", ""
    parts = rest.split(maxsplit=1)
    action = parts[0].lower()
    # Unknown dotted input is not public chat, but should not be accepted as a
    # farm action either. Keep this closed set synchronized with dispatch_farm.
    known = {
        "status", "st", "join", "move", "drop", "rest", "booster", "aggro",
        "quest", "sell", "bank", "attack", "cell", "cells", "combat",
        "capture", "chat", "goal", "area", "class", "auto", "item", "equip",
        "weapon", "armor", "helm", "cape", "level", "leveling", "dapat", "wiki", "resep",
        "saranfarm", "tambahakun", "editakun", "hapusakun", "daftarakun", "daftar", "kenapa", "help", "dashboard", "ui",
    }
    if action not in known:
        return "", ""
    if action == "leveling":
        action = "level"
    if action == "daftar":
        action = "daftarakun"
    if action == "ui":
        action = "dashboard"
    return action, (parts[1].strip() if len(parts) > 1 else "")


import re

def _print_menu(title: str, rows: list[str], prompt: str) -> None:
    count = 0
    clean_rows = []
    for row in rows:
        match = re.match(r"^\[(\d+)\]\s*(.*)", row)
        if match:
            count += 1
            clean_rows.append(f"  {match.group(1)}. {match.group(2)}")
        else:
            clean_rows.append(f"  {row}")
    if count > 0:
        print(f"[{title.upper()}] {count} {title.lower()} ditemukan:")
    else:
        print(f"[{title.upper()}]")
    for r in clean_rows:
        print(r)
    if prompt:
        print(f"[{title.upper()}] pilih: {prompt}")

def parse_account_credentials(arg: str) -> tuple[str, str]:
    """Parse '<username>,<password>' or '<username> <password>' (space-split fallback).

    The comma separator is the canonical form and supports usernames with spaces.
    Strips leading/trailing whitespace from both parts; raises ValueError on
    empty username, empty password, or missing separator entirely.
    """
    text = str(arg or "").strip()
    if "," in text:
        username, _, password = text.partition(",")
        username = username.strip()
        password = password.strip()
    else:
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            raise ValueError("format: .tambahakun <username>,<password>  contoh: .tambahakun user dengan spasi,katasandi")
        username, password = parts[0].strip(), parts[1].strip()
    if not username:
        raise ValueError("username tidak boleh kosong")
    if not password:
        raise ValueError("password tidak boleh kosong")
    return username, password


def _farm_wiki(orch: Any):
    """Reuse one read-only Wiki handle for the lifetime of the farm session."""
    wiki = getattr(orch, "_wiki_knowledge", None)
    if wiki is None:
        from .wiki_knowledge import WikiKnowledge, default_wiki_db_path

        wiki = WikiKnowledge(default_wiki_db_path())
        setattr(orch, "_wiki_knowledge", wiki)
    return wiki


def dispatch_farm(orch: Any, action: str, arg: str) -> str | None:
    """Jalankan satu perintah farming; error dilaporkan, tidak mematikan bot."""
    runtime = getattr(orch, "farming", None)
    bot = orch.bot
    if runtime is None:
        print("[WARN] runtime farming tidak tersedia.")
        return None
    try:
        if action == "dashboard":
            print("\n" + "=" * 56)
            for line in farm_dashboard_lines(orch):
                print(line)
            print("=" * 56)
        elif action == "help":
            print_farm_help()
        elif action in ("status", "st"):
            print(f"[FARM] {runtime.status()}")
        elif action == "join":
            target, private = _private_requested(arg)
            runtime.join(target, private=private)
        elif action == "move":
            x, y = (int(v) for v in arg.replace(",", " ").split()[:2])
            runtime.move(x, y)
        elif action == "drop":
            runtime.pickup_drop(int(arg.split()[0]))
        elif action == "rest":
            runtime.rest()
        elif action == "booster":
            runtime.use_booster(int(arg.split()[0]))
        elif action == "aggro":
            ids = [int(v) for v in arg.replace(",", " ").split()]
            runtime.aggro(ids)
        elif action == "quest":
            parts = arg.split()
            quest_id = int(parts[0])
            reward = int(parts[1]) if len(parts) > 1 else -1
            turn_ins = parts[2] if len(parts) > 2 else ""
            runtime.complete_quest(quest_id, reward, turn_ins)
        elif action == "sell":
            item_id, qty, char_item_id = (int(v) for v in arg.split()[:3])
            runtime.sell(item_id, qty, char_item_id)
        elif action == "bank":
            parts = arg.split()
            if not parts or parts[0] == "load":
                runtime.load_bank()
            elif parts[0] in ("in", "to") and len(parts) >= 3:
                runtime.bank_to_inventory(int(parts[1]), int(parts[2]))
            elif parts[0] in ("out", "from") and len(parts) >= 3:
                runtime.bank_from_inventory(int(parts[1]), int(parts[2]))
            else:
                print("[WARN] format: .bank load | in <item_id> <char_item_id> | out <item_id> <char_item_id>")
        elif action == "class":
            parts = arg.split(maxsplit=1)
            sub = parts[0].lower() if parts else ""
            value = parts[1].strip() if len(parts) > 1 else ""
            if not sub or sub in {"scan", "list", "ls"}:
                rows = runtime.scan_classes() if sub != "list" and sub != "ls" else runtime.class_report()
                _print_menu("Class", rows, ".class <nomor> atau .class <nama class>")
            elif sub in {"use", "equip", "pakai"} and value:
                print(f"[CLASS] {runtime.select_class(value)}")
            else:
                # Short flow: `.class 2` or `.class Legion Revenant`.
                print(f"[CLASS] {runtime.select_class(arg.strip())}")
        elif action in {"weapon", "armor", "helm", "cape"}:
            item_type = {
                "weapon": "Weapon",
                "armor": "Armor",
                "helm": "Helm",
                "cape": "Cape",
            }[action]
            if not arg.strip():
                rows = runtime.scan_gear(item_type)
                _print_menu(
                    action,
                    rows,
                    f".{action} <nomor> atau .{action} <nama item>",
                )
            else:
                print(
                    f"[{action.upper()}] "
                    f"{runtime.equip_gear(item_type, arg.strip())}"
                )
        elif action == "attack":
            if not arg.strip():
                runtime.attack("")
            elif arg.strip().lower() in {"off", "stop", "0"}:
                runtime.stop_attack()
            else:
                runtime.attack(arg)
        elif action == "combat":
            print(f"[COMBAT] {runtime.combat_status()}")
            report = getattr(runtime, "combat_scan_report", lambda: [])()
            if not report:
                print("[SCAN] belum ada snapshot monster dari moveToArea")
            else:
                for row in report:
                    print(f"[SCAN] {row}")
        elif action == "area":
            value = arg.strip().lower()
            if value in {"json", "--json"}:
                print(runtime.area_json())
            elif not value:
                for row in runtime.area_report():
                    print(f"[AREA] {row}")
            else:
                raise ValueError("format: .area [json]")
        elif action == "goal":
            value = arg.strip().lower()
            if value in {"clear_map", "clear", "map"}:
                runtime.fight_all_in_map()
            elif value in {"stop", "off", ""}:
                runtime.stop_goal()
            else:
                raise ValueError("format: .goal map|stop")
        elif action == "cell":
            parts = arg.split()
            if not parts:
                raise ValueError("format: .cell <nama> [pad]")
            cell = parts[0]
            pad = parts[1] if len(parts) > 1 else None
            target_cell, target_pad = runtime.move_to_cell(cell, pad)
            print(f"[CELL] pindah ke {target_cell}/{target_pad}")
        elif action == "cells":
            report = getattr(runtime, "cell_scan_report", lambda: [])()
            if not report:
                print("[CELL] belum ada moveToArea; join map dulu")
            else:
                for row in report:
                    print(f"[CELL] {row}")
        elif action == "chat":
            runtime.chat(arg)
        elif action == "capture":
            value = arg.strip().lower()
            if value not in {"on", "off", "1", "0"}:
                raise ValueError("format: .capture on|off")
            runtime.set_combat_capture(value in {"on", "1"})
        elif action == "auto":
            planner = getattr(bot, "auto_planner", None)
            if planner is None:
                print("[WARN] auto_planner tidak tersedia di mode ini.")
                return None
            if arg == "":
                # Empty means: garbage auto command like "auto" alone.
                print("[WARN] tujuan auto tidak dikenal. Contoh: auto cari Bone x5 dari Skeleton")
                return None
            from .auto_planner import AutoGoal  # local: cli.py loads at startup
            if arg in ("stop", "berhenti", "status"):
                if arg == "status":
                    print(f"[AUTO] {planner.status()}")
                else:
                    planner.stop()
                    print("[AUTO] tujuan dihentikan.")
            elif isinstance(arg, AutoGoal):
                # Farm-style goals run the planner loop; refusing unknown ones early.
                runtime.set_auto_goal(arg)
                print(f"[AUTO] {planner.status()}")
            else:
                print("[WARN] tujuan auto tidak dikenal. Contoh: auto cari Bone x5 dari Skeleton")
                return None
        elif action == "resep":
            if not arg.strip():
                raise ValueError("format: .resep <nama item>")
            tree = _farm_wiki(orch).resolve_recipe(arg.strip(), depth=3)
            if tree is None:
                print("[RESEP] item tidak ditemukan atau tidak ada bahan di database.")
            else:
                print(f"[RESEP] {tree}")
        elif action in {"dapat", "wiki"}:
            if not arg.strip():
                raise ValueError("format: .dapat <nama item>")
            wiki = _farm_wiki(orch)
            query = arg.strip()
            hit = (
                wiki.lookup_item(query)
                or wiki.lookup_location(query)
                or wiki.lookup_quest(query)
            )
            if hit is None:
                print("[WIKI] tidak ketemu di database lokal.")
            else:
                print(f"[WIKI] {hit.answer}")
        elif action == "saranfarm":
            if not arg.strip():
                raise ValueError("format: .saranfarm <nama monster>")
            suggestion = _farm_wiki(orch).suggest_farm(arg.strip())
            if not suggestion:
                print("[WIKI] tidak ada lokasi monster itu di database lokal.")
            else:
                print(f"[WIKI] {suggestion}")
        elif action == "tambahakun":
            try:
                username, password = parse_account_credentials(arg)
            except ValueError as exc:
                print(f"[AKUN] {exc}")
                return None
            accounts = getattr(orch, "accounts", None)
            if accounts is None:
                print("[AKUN] penyimpanan multi-akun tidak tersedia.")
                return None
            accounts.add_account(username, password)
            print(f"[AKUN] '{username}' tersimpan terenkripsi. /gantiakun di Telegram siap.")
        elif action == "editakun":
            try:
                username, password = parse_account_credentials(arg)
            except ValueError as exc:
                print(f"[AKUN] {exc}")
                return None
            accounts = getattr(orch, "accounts", None)
            if accounts is None:
                print("[AKUN] penyimpanan multi-akun tidak tersedia.")
                return None
            if username not in accounts.list_usernames():
                print(f"[AKUN] '{username}' tidak ada. Gunakan .tambahakun dulu, atau cek ejaan via .daftarakun.")
                return None
            accounts.add_account(username, password)
            print(f"[AKUN] password '{username}' diperbarui.")
        elif action == "hapusakun":
            username = arg.strip()
            if not username:
                print("[AKUN] format: .hapusakun <username>")
                return None
            accounts = getattr(orch, "accounts", None)
            if accounts is None:
                print("[AKUN] penyimpanan multi-akun tidak tersedia.")
                return None
            ok = accounts.remove_account(username)
            if ok:
                print(f"[AKUN] '{username}' berhasil dihapus.")
            else:
                print(f"[AKUN] '{username}' tidak ditemukan di daftar akun.")
        elif action == "daftarakun":
            accounts = getattr(orch, "accounts", None)
            if accounts is None:
                print("[AKUN] penyimpanan multi-akun tidak tersedia.")
                return None
            usernames = accounts.list_usernames()
            active = getattr(accounts, "active_username", lambda: None)()
            if not usernames:
                print("[AKUN] belum ada akun tersimpan. Gunakan .tambahakun <user>,<pass>.")
            else:
                print(f"[AKUN] {len(usernames)} akun tersimpan:")
                for u in usernames:
                    marker = " (aktif)" if u == active else ""
                    print(f"  {u}{marker}")
        elif action == "kenapa":
            reason = getattr(runtime, "last_reason", None)
            recovery = getattr(runtime, "last_recovery", None) or []
            if reason is None:
                print("[REASON] belum ada kegagalan tercatat; bot berjalan normal.")
            else:
                from .reasoning_engine import format_diagnosis_log
                print(format_diagnosis_log(reason, recovery))
        elif action == "item":
            parts = arg.split(maxsplit=1)
            sub = parts[0].lower() if parts else "scan"
            value = parts[1].strip() if len(parts) > 1 else ""
            if sub == "scan":
                rows = runtime.scan_items()
                _print_menu("Item", rows, ".equip <nomor> atau .equip <nama item>")
            elif sub == "list":
                rows = runtime.item_report("")
                _print_menu("Item", rows, ".equip <nomor> atau .equip <nama item>")
            elif sub == "type" and value:
                rows = runtime.item_report(value)
                _print_menu("Item", rows, ".equip <nomor> atau .equip <nama item>")
            else:
                raise ValueError("format: .item scan | list | type <tipe>")
        elif action in ("level", "leveling"):
            target, private = _private_requested(arg)
            if target in ("stop", "off", "berhenti"):
                print(f"[LEVEL] {runtime.stop_leveling()}")
            else:
                goal = 100
                if target and target.isdigit():
                    goal = int(target)
                print(f"[LEVEL] {runtime.start_leveling(goal, private=private)}")
        elif action == "equip":
            if not arg.strip():
                raise ValueError("format: .equip <nomor|nama item>")
            print(f"[EQUIP] {runtime.equip_item(arg.strip())}")
        else:
            print(f"[WARN] perintah farming '{action}' tidak dikenal.")
            return None
    except Exception as exc:
        print(f"[ERROR] farming {action}: {exc}")
        return "farm_error"
    print("[FARM] perintah terkirim.")
    return "farm"


def farm_menu_loop(orch: Any) -> None:
    """Loop interaktif khusus mode farming (tanpa AI/Admin)."""
    bot = orch.bot
    print_farm_banner(orch)
    while True:
        try:
            line = input(farm_prompt(orch)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT] Menghentikan bot...")
            bot.stop()
            break
        if not line:
            continue

        action, arg = parse_farm_command(line)
        if action:
            dispatch_farm(orch, action, arg)
            continue

        act, arg2 = parse_command(line)
        if act == "quit":
            print("[EXIT] Menutup bot...")
            bot.stop()
            break
        if act == "help":
            print_farm_banner(orch)
            continue
        if act == "noop":
            continue
        dispatch(bot, act, arg2)


def multi_farm_menu_loop(mo: Any) -> None:
    """Loop interaktif untuk mode multi-akun (MultiOrchestrator)."""
    n = mo.slot_count()
    print(f"\n{'='*56}")
    print(f"  SKUA-LITE MULTI-BOT ({n} akun aktif)")
    print(f"{'='*56}")
    for username, orch in mo.slots():
        bot = getattr(orch, "bot", None)
        state = getattr(bot, "state", "?") if bot else "OFFLINE"
        state = getattr(state, "value", state)
        current_map = getattr(bot, "current_map", "?") if bot else "-"
        print(f"  [{username}] {state} | {current_map}")
    print(f"{'='*56}")
    print("  Semua perintah farming (.level, .join, .attack, dll) dikirim ke SEMUA akun.")
    print("  .daftar  -> status semua akun | quit -> keluar\n")

    while True:
        try:
            prompt = f"[multi/{n}akun] > "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT] Menghentikan semua bot...")
            for _u, orch in mo.slots():
                try:
                    orch.bot.stop()
                except Exception:
                    pass
            break

        if not line:
            continue

        norm = line.strip().lower()

        if norm in {"quit", "exit", "keluar"}:
            print("[EXIT] Menutup semua bot...")
            for _u, orch in mo.slots():
                try:
                    orch.bot.stop()
                except Exception:
                    pass
            break

        if norm in {".daftar", "daftar", "status", ".status"}:
            print(mo.dashboard_text())
            continue

        action, arg = parse_farm_command(line)
        if action:
            results = mo.broadcast(action, arg)
            print(mo.format_broadcast(results))
        else:
            print("[WARN] perintah tidak dikenal; ketik .help atau .daftar")


def print_banner(bot: Any) -> None:
    print("\n" + "=" * 56)
    print("           SKUA-LITE (Python AQW Bot)             ")
    print("=" * 56)
    print(f" User   : {bot.username}")
    print(f" Server : {bot.server.name} ({bot.server.ip}:{bot.server.port})")
    print(f" Map    : {bot.current_map} (room #{bot.room_id})")
    print(f" Status : {bot.state.value} | AFK: {bot.is_afk}")
    print("-" * 56)
    print(" MENU UTAMA:")
    print("   [1] CHAT     -> kirim chat ke room/zone (ketik: chat <pesan>)")
    print("   [2] ACTION   -> reload, logout, minimize (ketik: action <nama>)")
    print("   [3] STATUS   -> cek kondisi bot")
    print("   [0] QUIT     -> keluar")
    print("-" * 56)
    print(" Shortcut cepat:")
    print("   chat <pesan>       | reload")
    print("   minimize (atau bg) | logout")
    print("=" * 56 + "\n")


def menu_loop(bot: Any) -> None:
    """Loop interaktif terminal."""
    print_banner(bot)
    while True:
        try:
            line = input("skua-lite> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT] Menghentikan bot...")
            bot.stop()
            break

        if not line:
            continue

        act, arg = parse_command(line)

        if act == "menu":
            if arg == "chat":
                msg = input("  Pesan chat: ").strip()
                if msg:
                    dispatch(bot, "chat", msg)
            elif arg == "action":
                print("  Pilihan ACTION:")
                print("    1. reload   (join ulang & re-afk)")
                print("    2. logout   (putus sesi)")
                print("    3. minimize (minimize terminal ke background)")
                print("    4. hide     (sembunyikan terminal total)")
                sub = input("  Pilih (1/2/3/4/nama): ").strip().lower()
                mapping = {"1": "reload", "2": "logout", "3": "minimize", "4": "hide"}
                target_sub = mapping.get(sub, sub)
                dispatch(bot, "action", target_sub)
            elif arg == "status":
                dispatch(bot, "status", "")
            elif arg == "quit":
                print("[EXIT] Menutup bot...")
                bot.stop()
                break
            continue

        if act == "quit":
            print("[EXIT] Menutup bot...")
            bot.stop()
            break

        if act == "help":
            print_banner(bot)
            continue

        dispatch(bot, act, arg)

        # Kalau user minta minimize, tetap loop di background
        if act == "action" and arg in ("minimize", "min", "bg", "hide"):
            # Console sudah diminimize, loop tetap jalan normal menerima input
            pass
