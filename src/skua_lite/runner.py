"""Orkestrasi end-to-end: prompt kredensial -> login -> pilih server -> join -> menu."""
from __future__ import annotations

import getpass
import os
import sys
import threading
import time
from typing import Any

from . import bot as bot_mod
from . import cli, config, credentials, farming, login, servers
from .credentials import CredentialStore, MultiAccountStore, NoStoredCredentials
from .auto_planner import AutoGoal
from .mode import RunMode, select_mode
from .reconnect import ReconnectPolicy
from .admin_commands import AdminActions, AdminCommandHandler
from .agent_tools import AgentTools
from .ai_router import AIChatRouter, AIConfig, openai_chat_generator
from .research import Researcher, ResearchCache
from .wiki_knowledge import WikiKnowledge, default_wiki_db_path
from .telegram_control import (
    TelegramConfig,
    TelegramControl,
    TelegramControlService,
    TelegramTransport,
)


class ReloginWatcher(threading.Thread):
    """Pantau state bot; bila koneksi putus, login ulang & join lagi.

    Retry dibatasi: ``ReconnectPolicy`` memberi jeda backoff eksponensial dan
    batas percobaan supaya bot mati dengan rapi kalau server benar-benar down,
    bukan menghajar login server tanpa henti.
    """

    def __init__(
        self,
        orchestrator: "Orchestrator",
        interval: float = 5.0,
        policy: ReconnectPolicy | None = None,
    ):
        super().__init__(name="ReloginWatcher", daemon=True)
        self.orch = orchestrator
        self.interval = interval
        self.policy = policy or ReconnectPolicy()
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        attempts = 0
        while not self._stop_event.is_set():
            # Poll with the base interval; the backoff only applies between
            # failed reconnect attempts, so a healthy bot is checked promptly.
            wait = self.policy.delay_for(attempts + 1) if attempts else self.interval
            if self._stop_event.wait(wait):
                return
            b = self.orch.bot
            if b is None:
                continue
            if b.state != bot_mod.BotState.DISCONNECTED_BY_SERVER:
                attempts = 0
                continue
            if not self.policy.should_retry(attempts):
                self.orch.log(
                    f"[RELOGIN] menyerah setelah {attempts} percobaan; bot dihentikan."
                )
                return
            attempts += 1
            self.orch.log(
                f"[RELOGIN] koneksi terputus, mencoba login ulang "
                f"(percobaan {attempts}/{self.policy.max_attempts})..."
            )
            try:
                self.orch.restart()
                self.orch.log("[RELOGIN] berhasil tersambung kembali.")
                attempts = 0
            except Exception as e:
                self.orch.log(f"[RELOGIN] gagal: {e}")


class Orchestrator:
    def __init__(
        self,
        server_name: str = config.DEFAULT_SERVER,
        target_map: str | None = None,
        store: credentials.CredentialStore | None = None,
        presence_capture_path: str | os.PathLike[str] | None = None,
        mode: RunMode = RunMode.ASSISTANT,
    ):
        self.mode = RunMode(mode)
        self.server_name = server_name
        # Mode menentukan tujuan default agar kedua flow tidak saling bercampur.
        if target_map is None:
            target_map = (
                config.DEFAULT_MAP
                if self.mode is RunMode.ASSISTANT
                else config.FARMING_MAP
            )
        self.target_map = target_map
        self.store = store or credentials.CredentialStore()
        self._accounts: MultiAccountStore | None = None
        self.bot: bot_mod.AQWBot | None = None
        self.watcher: ReloginWatcher | None = None
        self.farming: farming.FarmingRuntime | None = None
        self.telegram: TelegramControlService | None = None
        self.auto_relogin = True
        self.packet_log_enabled = False  # default: packet spam MATI
        self.last_inbound_packet = ""
        self.last_inbound_packet_time = 0.0
        capture = presence_capture_path or os.path.join(os.getcwd(), "presence_capture.log")
        self.presence_capture_path = os.fspath(capture)
        # Start every live run with a fresh evidence file.
        try:
            with open(self.presence_capture_path, "w", encoding="utf-8") as handle:
                handle.write("")
        except OSError:
            pass

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    @property
    def accounts(self) -> MultiAccountStore:
        """Lazy-init MultiAccountStore; konstruksi di-defer agar test yang pakai Mock store tidak pecah."""
        if self._accounts is None:
            self._accounts = MultiAccountStore(base_dir=self.store.base_dir)
        return self._accounts

    # ------------------------------------------------------------------
    def obtain_credentials(self) -> tuple[str, str]:
        """Ambil kredensial: dari storage terenkripsi, atau prompt user."""
        if self.store.exists():
            try:
                u, p = self.store.load()
                self.log(f"[AUTH] Kredensial tersimpan ditemukan untuk akun '{u}'.")
                use = input("Gunakan kredensial tersimpan? [Y/n]: ").strip().lower()
                if use in ("", "y", "ya", "yes"):
                    return u, p
            except credentials.NoStoredCredentials:
                pass

        print("\n[LOGIN] Masukkan kredensial akun AQW (tidak akan ditampilkan di layar).")
        username = input("  Username : ").strip()
        password = getpass.getpass("  Password : ")
        if not username or not password:
            raise RuntimeError("username/password kosong")

        save = input("  Simpan kredensial terenkripsi untuk auto-relogin? [Y/n]: ").strip().lower()
        if save in ("", "y", "ya", "yes"):
            self.store.save(username, password)
            self.log(f"[AUTH] Kredensial tersimpan terenkripsi di: {self.store.cred_file}")
        return username, password

    def connect(self, username: str, password: str) -> None:
        self.log("[HTTP] Autentikasi ke server AQW...")
        tok = login.aqw_login(username, password)
        self.log(f"[HTTP] Login berhasil. Akun: {tok.username}")

        self.log(f"[SRV] Mengambil daftar server & memilih '{self.server_name}'...")
        srv_list = servers.fetch_server_list()
        server = servers.pick(srv_list, self.server_name)
        self.log(f"[SRV] {server.name} -> {server.ip}:{server.port}")

        local_data = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "skua-lite",
        )
        ai_router = None
        # The assistant stack is never constructed in FARMING mode: no model,
        # researcher, Admin inbox, or Hermes tool subprocess can run there.
        if self.mode is RunMode.ASSISTANT:
            ai_config = AIConfig.from_env()
            if ai_config.configured:
                os.makedirs(local_data, exist_ok=True)
                researcher = Researcher(
                    ResearchCache(os.path.join(local_data, "research_cache")),
                    search_url=os.getenv("SKUA_RESEARCH_URL") or None,
                    wayback_api=os.getenv("SKUA_RESEARCH_WAYBACK") or None,
                    timeout=float(os.getenv("SKUA_RESEARCH_TIMEOUT", "8")),
                    page_timeout=float(os.getenv("SKUA_RESEARCH_PAGE_TIMEOUT", "12")),
                )
                b = None  # filled below; admin game actions close over it
                tools = AgentTools(
                    os.path.abspath(os.getcwd()),
                    agent_command=os.getenv("SKUA_AGENT_COMMAND", "hermes"),
                    timeout=float(os.getenv("SKUA_ADMIN_TIMEOUT", "600")),
                    code_timeout=float(os.getenv("SKUA_ADMIN_CODE_TIMEOUT", "30")),
                    shell_enabled=os.getenv("SKUA_ADMIN_SHELL", "0") == "1",
                )
                actions = AdminActions(
                    join_map=lambda target: _admin_join(b, target),
                    move=lambda x, y: _admin_move(b, x, y),
                    describe_status=lambda: f"state {_admin_status(b)}",
                )
                admin_handler = AdminCommandHandler(
                    tools=tools, actions=actions, on_log=self.log,
                    wiki=WikiKnowledge(default_wiki_db_path()),
                )
                ai_router = AIChatRouter(
                    generator=openai_chat_generator(ai_config),
                    send_chat=lambda message: b.send_plain_chat(message, channel="zone"),
                    on_log=self.log,
                    memory_path=os.path.join(local_data, "ai_memory.json"),
                    researcher=researcher,
                    admin_handler=admin_handler,
                    wiki=admin_handler.wiki,
                )
                self.log("[AI] router siap + Admin mode (owner `!` commands).")
            else:
                self.log("[AI] belum dikonfigurasi; isi SKUA_AI_BASE_URL/API_KEY/MODEL.")
        else:
            self.log("[FARM] flow farming aktif; AI, Admin, dan riset tidak dimuat.")

        self.log(f"[TCP] Menghubungkan & handshake SmartFox...")
        b = bot_mod.AQWBot(
            username=tok.username,
            token=tok.token,
            server=server,
            target_map=self.target_map,
            on_log=self.log,
            on_packet=self._on_packet,
            ai_router=ai_router,
            level=tok.level,
        )
        b.orchestrator = self
        if self.mode is RunMode.FARMING:
            # Farming stays active and never AFKs; the runtime also clears any
            # assistant state so a farming process cannot answer or run `!`.
            b.move_on_join = None
            b.afk_on_join = False
            b.ai_router = None
            self.farming = farming.FarmingRuntime(bot=b, on_log=self.log)
        else:
            self.farming = None
        b.start()
        self.bot = b
        if self.farming is not None:
            self.farming.start()
            self.log(f"[FARM] tersedia: {self.farming.status()}")
        self.log(f"[OK] Bot sudah berada di map '{b.current_map}' (room #{b.room_id})"
                 + (" dan AFK." if b.is_afk else " dan ACTIVE."))

        if self.auto_relogin and (self.watcher is None or not self.watcher.is_alive()):
            self.watcher = ReloginWatcher(self)
            self.watcher.start()
            self.log("[RELOGIN] Watcher aktif (interval 5s).")

    def _restore_state(self, snap: dict[str, Any]) -> None:
        """Apply a saved state snapshot to the newly created bot."""
        if not self.bot:
            return
        
        goal: AutoGoal | None = snap.get("goal")
        if goal is not None and self.farming:
            self.farming.auto_planner.set_goal(goal)
            
        follow_on: bool = snap.get("follow_on", False)
        if follow_on:
            self.bot.follow.start(
                owner_name=snap.get("follow_name", ""),
                owner_id=snap.get("follow_id")
            )

    def restart(self) -> None:
        """Relogin & join ulang (dipakai auto-relogin)."""
        u, p = self.store.load()
        snap = {}
        if self.bot:
            try:
                # Capture current map to join it instead of the default
                if self.bot.current_map:
                    self.target_map = self.bot.current_map
                
                # Capture follow state
                snap["follow_on"] = self.bot.follow.is_following
                snap["follow_name"] = self.bot.follow.owner_name
                snap["follow_id"] = self.bot.follow.owner_id
                
                # Capture goal
                if self.farming and self.farming.auto_planner.active:
                    snap["goal"] = self.farming.auto_planner.current_goal

                self.bot.stop()
            except Exception:
                pass
        self.connect(u, p)
        self._restore_state(snap)

    def switch_server(self, server_name: str) -> str:
        """Ganti server tujuan dan reconnect bot."""
        name = str(server_name or "").strip()
        if not name:
            return "Nama server tidak boleh kosong."
        try:
            srv_list = servers.fetch_server_list()
            server = servers.pick(srv_list, name)
        except servers.ServerUnavailable as e:
            return f"Gagal ganti server: {e}"
        except Exception as e:
            return f"Gagal mengambil daftar server: {e}"

        self.server_name = server.name
        try:
            self.restart()
            return f"Berhasil berpindah ke server {server.name}."
        except Exception as e:
            return f"Gagal koneksi ke server {server.name}: {e}"

    def switch_account(self, username: str, password: str) -> str:
        """Ganti akun, simpan terenkripsi ke kedua store, lalu koneksi."""
        u = str(username or "").strip()
        p = str(password or "").strip()
        if not u or not p:
            return "Username dan password wajib diisi."

        self.store.save(u, p)
        self.accounts.add_account(u, p)
        if self.bot:
            try:
                self.bot.stop()
            except Exception:
                pass

        try:
            self.connect(u, p)
            return f"Berhasil login sebagai '{u}'."
        except Exception as e:
            return f"Gagal login akun baru: {e}"

    def switch_account_by_name(self, username: str) -> str:
        """Ganti ke akun tersimpan lain tanpa memasukkan ulang password."""
        u = str(username or "").strip()
        if not u:
            return "Nama akun tidak boleh kosong."
        try:
            _, password = self.accounts.load(u)
        except NoStoredCredentials:
            # Cek apakah itu akun di legacy store
            if self.store.exists():
                try:
                    leg_u, leg_p = self.store.load()
                    if leg_u.casefold() == u.casefold():
                        return self.switch_account(leg_u, leg_p)
                except Exception:
                    pass
            return f"Akun '{u}' tidak ditemukan di daftar tersimpan."
        except Exception as e:
            return f"Gagal membaca akun '{u}': {e}"

        self.accounts.set_active(u)
        return self.switch_account(u, password)

    def start_telegram_control(self, config: TelegramConfig | None = None) -> bool:
        """Start one owner-only Telegram long-poll controller when configured."""
        if self.mode is not RunMode.FARMING or self.farming is None or self.bot is None:
            return False
        cfg = config or TelegramConfig.from_env()
        if not cfg.enabled:
            return False
        if self.telegram is not None:
            self.telegram.stop()
        control = TelegramControl(
            self,
            TelegramTransport(cfg.token),
            owner_id=cfg.owner_id,
            run_command=cli.dispatch_farm,
        )
        service = TelegramControlService(control, on_log=self.log)
        service.start()
        self.telegram = service
        if cfg.owner_id is None:
            self.log(
                "[TELEGRAM] owner belum dikunci; kirim /start untuk melihat "
                "numeric ID, lalu isi SKUA_TELEGRAM_OWNER_ID."
            )
        return True

    def _on_packet(self, pkt: str, outbound: bool) -> None:
        # Keep the most recent server packet for one-shot diagnostics and append
        # system presence events to an evidence file. Only structural SFS/game
        # events are captured; chat bodies and credentials are never written.
        if not outbound:
            self.last_inbound_packet = pkt
            self.last_inbound_packet_time = time.time()
            self._capture_presence(pkt)
            if self.farming is not None:
                try:
                    self.farming.feed_packet(pkt)
                except Exception:
                    pass
        else:
            if self.farming is not None:
                try:
                    self.farming.feed_packet(pkt, outbound=True)
                except Exception:
                    pass
        # Packet log only active when explicitly requested (action log on).
        if not self.packet_log_enabled:
            return
        arrow = ">>" if outbound else "<<"
        short = pkt if len(pkt) <= 160 else pkt[:157] + "..."
        self.log(f"  {arrow} {short}")

    _PRESENCE_MARKERS = (
        "action='uER'",
        'action="uER"',
        "action='userGone'",
        'action="userGone"',
        '"cmd":"initUserData"',
        '"cmd": "initUserData"',
        '"cmd":"initUserDatas"',
        '"cmd": "initUserDatas"',
    )

    def _capture_presence(self, pkt: str) -> None:
        """Append SFS/game presence events to the evidence file (no chat text)."""
        if not any(marker in pkt for marker in self._PRESENCE_MARKERS):
            return
        stamp = time.strftime("%H:%M:%S")
        try:
            with open(self.presence_capture_path, "a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {pkt[:1000]}\n")
        except OSError:
            pass

    def dump_presence(self) -> None:
        """Print captured presence evidence for post-run analysis."""
        self.log(f"[DEBUG] file bukti: {self.presence_capture_path}")
        age = (
            f"{time.time() - self.last_inbound_packet_time:.1f}s lalu"
            if self.last_inbound_packet_time
            else "belum ada"
        )
        self.log(f"[DEBUG] paket masuk terakhir ({age}):")
        self.log(f"        {self.last_inbound_packet[:600] or '(kosong)'}")
        try:
            with open(self.presence_capture_path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            self.log(f"[DEBUG] gagal membaca bukti: {exc}")
            return
        if not lines:
            self.log("[DEBUG] belum ada event presence (uER/initUserData) tercatat.")
            return
        self.log(f"[DEBUG] {len(lines)} event presence tercatat:")
        for line in lines[-20:]:
            self.log(f"        {line}")

    def dump_last_packet_to_file(self) -> str:
        """Write the last inbound packet to disk and return the path."""
        path = os.path.join(os.getcwd(), "last_packet.txt")
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.last_inbound_packet)
        except OSError:
            return ""
        return path

    def shutdown(self) -> None:
        if self.telegram:
            self.telegram.stop()
        if self.watcher:
            self.watcher.stop()
        if self.farming:
            self.farming.stop()
        if self.bot:
            self.bot.stop()


def _admin_join(bot: bot_mod.AQWBot | None, target: str) -> bool:
    """Game action adapter for `!join`; success means no BotError was raised."""
    if bot is None:
        return False
    bot.join_map(target)
    return True


def _admin_move(bot: bot_mod.AQWBot | None, x: int, y: int) -> bool:
    """Game action adapter for `!move`."""
    if bot is None:
        return False
    bot.move(x, y)
    return True


def _admin_status(bot: bot_mod.AQWBot | None) -> str:
    if bot is None:
        return "belum tersambung"
    return (
        f"{bot.state.value}, map {bot.current_map}, room {bot.room_id}, "
        f"AFK {'on' if bot.is_afk else 'off'}"
    )



def run_multi(
    server_name: str = config.DEFAULT_SERVER,
    target_map: str | None = None,
    *,
    accounts: MultiAccountStore | None = None,
) -> int:
    """Login semua akun tersimpan dan kontrol sebagai satu kelompok farming."""
    from .multi_session import MultiOrchestrator

    account_store = accounts or MultiAccountStore()
    usernames = account_store.list_usernames()
    if not usernames:
        print(
            "[MULTI] belum ada akun tersimpan. Jalankan mode farming tunggal, "
            "lalu gunakan .tambahakun <username>,<password>.",
            file=sys.stderr,
        )
        return 2

    group = MultiOrchestrator(accounts=account_store, server_name=server_name)
    failures: list[str] = []
    for username in usernames:
        try:
            _u, password = account_store.load(username)
            slot_store = credentials.CredentialStore(
                base_dir=account_store.base_dir / "slots" / username
            )
            slot_store.save(username, password)
            orch = Orchestrator(
                server_name=server_name,
                target_map=target_map,
                store=slot_store,
                mode=RunMode.FARMING,
                presence_capture_path=account_store.base_dir / f"presence_{username}.log",
            )
            orch.auto_relogin = True
            print(f"[MULTI] login akun '{username}'...")
            orch.connect(username, password)
            group.add_slot(username, orch)
            print(f"[MULTI] '{username}' aktif.")
        except Exception as exc:
            failures.append(f"{username}: {exc}")
            print(f"[MULTI] '{username}' gagal: {exc}", file=sys.stderr)

    if group.slot_count() == 0:
        print("[MULTI] tidak ada akun yang berhasil login.", file=sys.stderr)
        return 1

    if failures:
        print(f"[MULTI] {len(failures)} akun gagal, {group.slot_count()} akun tetap aktif.")

    try:
        started = group.start_telegram_control()
        if not started:
            print("[TELEGRAM] tidak dikonfigurasi; isi .env untuk mengaktifkan.")
        cli.multi_farm_menu_loop(group)
    finally:
        group.shutdown()
    return 0

def run(server_name: str = config.DEFAULT_SERVER, target_map: str | None = None,
        store: credentials.CredentialStore | None = None,
        mode: str | RunMode | None = None, multi: bool = False) -> int:
    """Entry point utama: pilih mode dulu, baru login (atau fan-out multi)."""
    try:
        selected = select_mode(mode)
    except ValueError as e:
        print(f"\n[ABORT] {e}", file=sys.stderr)
        return 2
    if multi:
        if selected is not RunMode.FARMING:
            print("[ABORT] --multi hanya tersedia untuk mode farming.", file=sys.stderr)
            return 2
        return run_multi(server_name=server_name, target_map=target_map)
    orch = Orchestrator(server_name=server_name, target_map=target_map,
                        store=store, mode=selected)
    try:
        username, password = orch.obtain_credentials()
        orch.connect(username, password)
    except (login.LoginFailed, servers.ServerUnavailable, bot_mod.BotError) as e:
        print(f"\n[FATAL] {e}", file=sys.stderr)
        orch.shutdown()
        return 1
    except RuntimeError as e:
        print(f"\n[ABORT] {e}", file=sys.stderr)
        return 2

    try:
        if orch.farming is not None:
            started = orch.start_telegram_control()
            if not started:
                print("[TELEGRAM] tidak dikonfigurasi; isi .env untuk mengaktifkan.")
            cli.farm_menu_loop(orch)
        else:
            cli.menu_loop(orch.bot)
    finally:
        orch.shutdown()
    return 0
