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


def print_farm_banner(orch: Any) -> None:
    bot = orch.bot
    print("\n" + "=" * 56)
    print("        SKUA-LITE  ** MODE FARMING **        ")
    print("=" * 56)
    print(f" User   : {bot.username}")
    print(f" Server : {bot.server.name} ({bot.server.ip}:{bot.server.port})")
    print(f" Map    : {bot.current_map} (room #{bot.room_id})")
    print(f" Status : {bot.state.value} | AFK: {bot.is_afk}")
    print(f" AI     : OFF (mode farming tidak memuat AI/Admin)")
    print("-" * 56)
    print(" PERINTAH FARMING (awali dengan titik):")
    print("   .status                   -> ringkasan runtime")
    print("   .join <map>               -> pindah map farm")
    print("   .move <x> <y>             -> gerak ke koordinat")
    print("   .drop <drop_id>           -> ambil drop")
    print("   .rest                     -> minta rest")
    print("   .booster <item_id>        -> pakai consumable")
    print("   .aggro <id> [id2 ...]     -> tarik monster by MonMapID")
    print("   .quest <id> [reward] [turnins]")
    print("   .sell <item_id> <qty> <char_item_id>")
    print("   .bank load|in|out ...     -> operasi bank")
    print("   .attack <nama>            -> auto-attack monster nama itu")
    print("   .attack auto              -> serang SEMUA monster hidup di cell")
    print("   .attack off               -> hentikan auto-attack")
    print("   .cell <nama> [pad]        -> pindah cell via moveToCell")
    print("   .cells                    -> daftar semua cell hasil scan map")
    print("   .combat                   -> status combat + daftar monster di-scan")
    print("   .area [json]              -> snapshot area dinamis + provenance")
    print("   .goal map                 -> lawan SEMUA musuh di map ini")
    print("   .goal stop                -> hentikan tujuan map")
    print("   (tanpa titik juga bisa: 'lawan semua musuh di map ini')")
    print("   .capture on|off           -> rekam paket combat ke combat_capture.log")
    print("   .chat <pesan|/command>    -> chat biasa atau cmd game (/join, /goto)")
    print("-" * 56)
    print(" Umum: chat <pesan> | status | quit")
    print("=" * 56 + "\n")


def _goal_noun(text: str) -> bool:
    words = set(text.replace("-", " ").split())
    return bool(words & {"musuh", "monster", "enemy", "enemies"})


_GOAL_VERBS = {"lawan", "serang", "habisi", "basmi", "bunuh", "clear"}


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
        "capture", "chat", "goal", "area", "class", "auto"
    }
    if action not in known:
        return "", ""
    return action, (parts[1].strip() if len(parts) > 1 else "")


def dispatch_farm(orch: Any, action: str, arg: str) -> str | None:
    """Jalankan satu perintah farming; error dilaporkan, tidak mematikan bot."""
    runtime = getattr(orch, "farming", None)
    bot = orch.bot
    if runtime is None:
        print("[WARN] runtime farming tidak tersedia.")
        return None
    try:
        if action in ("status", "st"):
            print(f"[FARM] {runtime.status()}")
        elif action == "join":
            runtime.join(arg)
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
            sub = parts[0].lower() if parts else "scan"
            value = parts[1].strip() if len(parts) > 1 else ""
            if sub in {"scan", "list", "ls"}:
                rows = runtime.scan_classes() if sub == "scan" else runtime.class_report()
                for index, row in enumerate(rows, 1):
                    print(f"[CLASS {index}] {row}")
                print("[CLASS] pilih: .class use <nama class>")
            elif sub in {"use", "equip", "pakai"} and value:
                print(f"[CLASS] {runtime.select_class(value)}")
            else:
                raise ValueError("format: .class scan | list | use <nama class>")
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
            if arg in ("stop", "berhenti"):
                planner.stop()
                print("[AUTO] tujuan dihentikan.")
            elif arg == "status":
                print(f"[AUTO] {planner.status()}")
            else:
                # arg is an AutoGoal parsed by parse_farm_command above
                from .auto_planner import AutoGoal  # avoid top-level circular
                if isinstance(arg, AutoGoal):
                    planner.set_goal(arg)
                    print(f"[AUTO] {planner.status()}")
                else:
                    print("[WARN] tujuan auto tidak dikenal. Contoh: auto cari Bone x5 dari Skeleton")
                    return None
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
            line = input("skua-farm> ").strip()
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
