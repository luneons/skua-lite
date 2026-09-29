"""State machine AQWBot: headless background worker.

Alur:
  1. TCP connect ke server Yorumi (atau server lain yang dipilih)
  2. Handshake: kirim verChk -> tunggu apiOK
  3. Login: kirim login XML -> tunggu logOK
  4. Lobby: kirim firstJoin
  5. Join Map: kirim cmd tfer -> tunggu joinOK -> simpan room_id
  6. AFK: kirim cmd afk
  7. Loop keep-alive di thread background, siap menerima perintah chat / action
"""
from __future__ import annotations

import enum
import threading
import time
from typing import Callable

from . import client, config, sfs
from .ai_router import is_owner_account, is_owner_id
from .servers import Server


class BotState(enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    VERCHK = "VERCHK"
    LOGGING_IN = "LOGGING_IN"
    LOGGED_IN = "LOGGED_IN"
    JOINING_MAP = "JOINING_MAP"
    IN_MAP = "IN_MAP"
    DISCONNECTED_BY_SERVER = "DISCONNECTED_BY_SERVER"
    STOPPED = "STOPPED"


class BotError(Exception):
    """Error fatal pada alur bot."""


CLIENT_VERSION_STRING = "4.372"  # Game.as vParam

# Accounts excluded from the deterministic Yulgar arrival greeting. Match both
# known SmartFox ID and normalized account name because session IDs can change.
_GREETING_EXCLUDED_IDS = frozenset({32017})
_GREETING_EXCLUDED_NAMES = frozenset({"sulcata3"})


def _is_greeting_excluded(user_id: int | None, username: str) -> bool:
    clean = " ".join((username or "").split()).casefold()
    return user_id in _GREETING_EXCLUDED_IDS or clean in _GREETING_EXCLUDED_NAMES


class AQWBot:
    def __init__(
        self,
        username: str,
        token: str,
        server: Server,
        target_map: str = config.DEFAULT_MAP,
        cell: str = config.DEFAULT_CELL,
        pad: str = config.DEFAULT_PAD,
        timeout: float = 15.0,
        on_log: Callable[[str], None] | None = None,
        on_packet: Callable[[str, bool], None] | None = None,  # (pkt, outbound)
        ai_router: object | None = None,
    ):
        self.username = username.lower()
        self.token = token
        self.server = server
        self.target_map = target_map
        self.cell = cell
        self.pad = pad
        self.timeout = timeout
        self.on_log = on_log or (lambda msg: None)
        self.on_packet = on_packet or (lambda p, out: None)
        self.ai_router = ai_router
        self._greeted_uids: set[int] = set()

        self.state: BotState = BotState.DISCONNECTED
        self.current_map: str = ""
        self.room_id: int = 1
        self.session_user_id: int | None = None
        self.is_afk: bool = False
        # Players seen in the latest area snapshot (`moveToArea.uoBranch`),
        # keyed by lowercase username -> (cell, pad, intState). Tracked for
        # area diagnostics and `/goto` local routing (see `World.goto`).
        self._area_players: dict[str, tuple[str, str, int | None]] = {}

        self._client: client.SFSClient | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state_cv = threading.Condition()
        # Hanya satu consumer boleh membaca socket. Tanpa lock ini, worker
        # background bisa merebut moveToArea yang sedang ditunggu /join.
        self._io_lock = threading.RLock()
        # Koordinat tujuan yang dikirim otomatis setelah mendarat di map.
        # None = tidak bergerak otomatis.
        self.move_on_join: tuple[int, int, int] | None = (
            config.DEFAULT_X, config.DEFAULT_Y, config.DEFAULT_MOVE_SPEED
        )
        # Mode farming mematikannya agar bot tidak AFK tanpa disuruh.
        self.afk_on_join: bool = True
        self._last_keepalive: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _set_state(self, new_state: BotState) -> None:
        with self._state_cv:
            self.state = new_state
            self.on_log(f"[STATE] -> {new_state.value}")
            self._state_cv.notify_all()

    def wait_for_state(self, target: BotState, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._state_cv:
            while self.state != target:
                rem = deadline - time.monotonic()
                if rem <= 0:
                    return False
                self._state_cv.wait(rem)
            return True

    def start(self) -> None:
        """Mulai proses koneksi & jalankan loop I/O di background thread."""
        self._stop_event.clear()
        self._set_state(BotState.CONNECTING)
        self._client = client.SFSClient(self.server.ip, self.server.port, timeout=self.timeout)
        try:
            self._client.connect()
        except client.ConnectionFailed as e:
            self._set_state(BotState.DISCONNECTED)
            raise BotError(f"koneksi ke server {self.server.name} gagal: {e}") from e

        # Jalankan handshake synchronous sampai IN_MAP (atau gagal), lalu loop
        self._perform_handshake()
        self._thread = threading.Thread(target=self._loop, name="AQWBot-Worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Hentikan bot dan tutup koneksi."""
        self._stop_event.set()
        if self._client and self._client.alive:
            try:
                self._send_raw(sfs.logout_packet(self.room_id))
            except Exception:
                pass
            self._client.close()
        self._set_state(BotState.STOPPED)

    # ------------------------------------------------------------------
    # Handshake & Join Flow
    # ------------------------------------------------------------------
    def _send_raw(self, pkt: bytes) -> None:
        if self._client is None:
            return
        self.on_packet(pkt.rstrip(b"\x00").decode("latin-1", errors="replace"), True)
        self._client.send(pkt)

    def _wait_for_packet(self, predicate: Callable[[str], bool], timeout: float) -> str:
        with self._io_lock:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not self._stop_event.is_set():
                pkt = self._client.recv_packet(timeout=0.3)
                if pkt is None:
                    continue
                self.on_packet(pkt, False)
                if predicate(pkt):
                    return pkt
        raise BotError(f"timeout menunggu paket yang cocok ({predicate.__name__ if hasattr(predicate, '__name__') else 'predicate'})")

    def _perform_handshake(self) -> None:
        # Step 1: verChk
        self._set_state(BotState.VERCHK)
        self._send_raw(sfs.verchk_packet())
        self._wait_for_packet(lambda p: "action='apiOK'" in p or "action='verChk'" in p or "<ver " in p, timeout=self.timeout)

        # Step 2: login zone_master
        self._set_state(BotState.LOGGING_IN)
        nick = f"{config.CLIENT_TOKEN}~{self.username}~{CLIENT_VERSION_STRING}"
        self._send_raw(sfs.login_packet(nick, self.token))

        def _is_login_reply(p: str) -> bool:
            return (
                "loginResponse" in p
                or "action='logOK'" in p
                or "action='logKO'" in p
            )

        login_resp = self._wait_for_packet(_is_login_reply, timeout=self.timeout)
        if "action='logKO'" in login_resp or "%false%" in login_resp:
            self._set_state(BotState.DISCONNECTED)
            raise BotError("login ditolak server")
        self.session_user_id = sfs.parse_login_user_id(login_resp)

        self._set_state(BotState.LOGGED_IN)

        # Step 3: firstJoin -> masuk ke world (server membalas joinOK room default,
        # kemudian moveToArea ke area awal, biasanya "battleon-1"). Karakter baru
        # boleh pindah map setelah server mengirim moveToArea (intState != 0);
        # kalau tfer dikirim saat masih loading, server mengabaikannya diam-diam.
        self._send_raw(sfs.get_room_list_packet(room=-1))
        self._send_raw(sfs.xt_str("zm", "firstJoin", [], room=1))

        first_join = self._wait_for_packet(
            lambda p: "action='joinOK'" in p,
            timeout=self.timeout,
        )
        world_room = sfs.parse_room_id(first_join)
        if world_room is not None:
            self.room_id = world_room
        self.on_log(f"[WORLD] masuk world (room #{self.room_id})")

        # Tunggu moveToArea -> itu tanda karakter benar-benar sudah di area awal.
        area = self._wait_for_move_to_area(timeout=self.timeout)
        if area is not None:
            self.on_log(f"[WORLD] area awal: {area[0]} (room #{area[1]})")
            self.current_map = area[0]
            self.room_id = area[1]
            self._home_map = area[0]

        # Client asli memanggil World.getInventory(uid) setelah initUserData.
        # Headless client tidak membangun avatar Flash, jadi request ini harus
        # dikirim eksplisit; tanpa ini tfer ditolak: "Inventory is being loaded".
        if self.session_user_id is not None:
            self._send_raw(sfs.retrieve_inventory_packet(
                room=self.room_id,
                user_id=self.session_user_id,
            ))
            try:
                self._wait_for_packet(
                    lambda p: "loadInventory" in p,
                    timeout=self.timeout,
                )
                self.on_log("[WORLD] inventory siap")
            except BotError:
                self.on_log("[WARN] inventory belum konfirmasi; tfer akan dicoba ulang")

        # Step 4: join target map (sekarang aman dikirim; _join_map_and_wait
        # sudah men-set self.current_map dari moveToArea server)
        self._set_state(BotState.JOINING_MAP)
        self.room_id = self._join_map_and_wait(self.target_map)

        self._set_state(BotState.IN_MAP)

        # Step 5: setelah benar-benar mendarat, gerak ke koordinat tujuan.
        # Gerak dilakukan sebelum AFK agar status akhir tetap AFK.
        if self.move_on_join is not None:
            x, y, sp = self.move_on_join
            try:
                self.move(x, y, sp)
            except BotError as e:
                self.on_log(f"[WARN] move otomatis dilewati: {e}")

        # Step 6: mode asisten AFK; mode farming tetap aktif.
        time.sleep(0.1)
        if self.afk_on_join:
            self.set_afk(True)
        else:
            self.is_afk = False
            self.on_log("[FARM] karakter tetap ACTIVE (AFK tidak dikirim)")
        self._last_keepalive = time.monotonic()

    def _wait_for_move_to_area(self, timeout: float | None = None) -> tuple[str, int] | None:
        """Tunggu sampai server mengirim moveToArea dengan karakter di area.

        Diperlukan karena tfer hanya berlaku saat intState != 0 (lihat
        Chat.as case 'join'). Bila timeout, kembalikan None dan kita tetap
        berusaha tfer (sesuai perilaku client asli).
        """
        to = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + to
        while time.monotonic() < deadline:
            pkt = self._wait_for_packet(
                lambda p: "moveToArea" in p,
                timeout=max(0.5, deadline - time.monotonic()),
            )
            area = sfs.parse_move_to_area(pkt)
            if area is not None:
                return area
        return None

    def _join_map_and_wait(self, map_name: str) -> int:
        """Kirim tfer dan tunggu moveToArea sebagai bukti pindah map sukses.

        Server menolak tfer selama inventory karakter belum selesai dimuat
        (balasan ``Character Inventory is being loaded``). Karena itu kita
        kirim ulang secara berkala sampai server benar-benar memindahkan
        karakter ke map tujuan.
        """
        deadline = time.monotonic() + self.timeout
        with self._io_lock:
            while time.monotonic() < deadline:
                self._send_raw(sfs.join_packet(
                    username=self.username,
                    map_name=map_name,
                    room=1,
                ))

                send_deadline = min(deadline, time.monotonic() + 2.5)
                while time.monotonic() < send_deadline:
                    try:
                        pkt = self._wait_for_packet(
                            lambda p: "moveToArea" in p or "warning" in p,
                            timeout=max(0.5, send_deadline - time.monotonic()),
                        )
                    except BotError:
                        break
                    area = sfs.parse_move_to_area(pkt)
                    if area is not None:
                        parsed = sfs.parse_xt_json(pkt)
                        if parsed is not None:
                            self.note_area_players(parsed.get("obj") or {})
                        self.current_map = area[0]
                        return area[1]
                    # warning (inventory loading) -> coba lagi setelah jeda
                    break
                time.sleep(0.8)
        raise BotError(f"server tidak memindahkan karakter ke {map_name}")

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if not self._client or not self._client.alive:
                self._set_state(BotState.DISCONNECTED_BY_SERVER)
                break

            # 1. Baca paket masuk (jangan rebut socket dari /join sinkron)
            if self._stop_event.is_set():
                break
            with self._io_lock:
                if not self._client or not self._client.alive or self._stop_event.is_set():
                    break
                pkt = self._client.recv_packet(timeout=0.3)
            if pkt:
                self.on_packet(pkt, False)
                self._handle_server_packet(pkt)

            # 2. Keepalive periodik
            now = time.monotonic()
            if now - self._last_keepalive >= config.KEEPALIVE_INTERVAL:
                self._send_keepalive()
                self._last_keepalive = now

        if self.state not in (BotState.STOPPED, BotState.DISCONNECTED_BY_SERVER):
            self._set_state(BotState.STOPPED)

    def _handle_server_packet(self, pkt: str) -> None:
        if "action='logout'" in pkt or "action='disconn'" in pkt:
            self._set_state(BotState.DISCONNECTED_BY_SERVER)
            return

        area = sfs.parse_xt_json(pkt)
        if area is not None and area.get("cmd") == "moveToArea":
            self.note_area_players(area.get("obj") or {})
            parsed_area = sfs.parse_move_to_area(pkt)
            if parsed_area is not None:
                self.current_map, self.room_id = parsed_area

        if self.ai_router is not None:
            user_enter = sfs.parse_user_enter_room(pkt)
            if user_enter is not None:
                self.ai_router.note_presence(
                    "masuk", user_enter["username"], user_enter["user_id"]
                )
                uid = user_enter["user_id"]
                # Owners get a richer AI greeting via the existing
                # owner_arrived path; other players get a deterministic
                # "Halo, <name>!" so the room feels alive. Self and bots are
                # skipped, and each UID is greeted only once per session.
                if (
                    uid is not None
                    and uid not in self._greeted_uids
                    and not is_owner_id(uid)
                    and not is_owner_account(user_enter["username"])
                    and not _is_greeting_excluded(uid, user_enter["username"])
                    and (
                        self.username is None
                        or user_enter["username"].lower() != self.username.lower()
                    )
                ):
                    self._greeted_uids.add(uid)
                    self.ai_router.user_arrived(user_enter["username"])
                if is_owner_id(uid) or is_owner_account(user_enter["username"]):
                    self._send_raw(sfs.retrieve_user_data_packet(
                        room=user_enter["room"],
                        user_id=user_enter["user_id"],
                    ))
                    # _send_raw only logs outbound packets; it does not feed them
                    # back through _handle_server_packet. The uER payload already
                    # proves this account entered the room, so lock and greet now.
                    self.ai_router.owner_arrived(uid, user_enter["username"])
                    return
            # The outbound retrieveUserData packet is also surfaced by packet
            # logging/captures and is treated as the owner's arrival signal.
            arrival = sfs.parse_retrieve_user_data(pkt)
            if arrival is not None:
                if self.ai_router.owner_arrived(arrival["user_id"]):
                    return
            init_data = sfs.parse_init_user_data(pkt)
            if init_data is not None:
                if self.ai_router.owner_arrived(init_data["user_id"]):
                    return
            user_gone = sfs.parse_user_gone(pkt)
            if user_gone is not None and user_gone["room"] in (-1, self.room_id):
                name = self.ai_router.seen_name(user_gone["user_id"])
                self.ai_router.note_presence("keluar", name, user_gone["user_id"])
                self._greeted_uids.discard(user_gone["user_id"])
                if self.ai_router.owner_left_location(user_id=user_gone["user_id"]):
                    return
            departure = sfs.parse_exit_area(pkt)
            if departure is not None:
                self.ai_router.note_presence(
                    "keluar", departure["username"], departure["user_id"]
                )
                self._greeted_uids.discard(departure["user_id"])
                if self.ai_router.owner_left_location(
                    departure["username"], departure["user_id"]
                ):
                    return

        chat = sfs.parse_chat_message(pkt)
        if chat is not None:
            sender = chat["sender"]
            channel = chat["channel"]
            msg = chat["message"]
            self.on_log(f"[{channel.upper()}] {sender}: {msg}")
            if self.ai_router is not None:
                self.ai_router.note_chat(sender, msg, channel)
                self.ai_router.handle_message(
                    msg,
                    sender,
                    is_self=sender.lower() == self.username.lower(),
                    sender_id=chat["user_id"],
                )

    def _send_keepalive(self) -> None:
        # Kirim roundTrip ping (XML sys) agar server tidak disconnect karena idle
        try:
            self._send_raw(sfs.round_trip_packet(self.room_id))
        except Exception as e:
            self.on_log(f"[WARN] keepalive gagal: {e}")

    # ------------------------------------------------------------------
    # Perintah / Aksi dari User
    # ------------------------------------------------------------------
    def note_area_players(self, area_obj: dict) -> None:
        """Index players from a `moveToArea` snapshot for area diagnostics.

        Mirrors `World.uoTree`, which the client builds from the same payload:
        `uoBranch` entries carry `uoName`, `strFrame` and `strPad`.
        """
        players: dict[str, tuple[str, str, int | None]] = {}
        for entry in area_obj.get("uoBranch", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("uoName") or entry.get("strUsername") or "").strip()
            if not name:
                continue
            cell = str(entry.get("strFrame") or "").strip()
            pad = str(entry.get("strPad") or "").strip() or "Spawn"
            state: int | None = None
            for key in ("intState", "intstate", "state"):
                raw = entry.get(key)
                if raw is None:
                    continue
                try:
                    state = int(raw)
                except (TypeError, ValueError):
                    continue
                break
            players[name.lower()] = (cell, pad, state)
        self._area_players = players

    def send_plain_chat(self, message: str, channel: str = "zone") -> None:
        """Kirim teks sebagai chat biasa tanpa menafsirkan slash-command."""
        if self.state != BotState.IN_MAP:
            raise BotError(f"tidak bisa chat saat bot berstatus {self.state.value}")
        clean = message.replace("%", "").strip()
        if not clean:
            return
        pkt = sfs.chat_packet(self.room_id, clean, channel=channel)
        self._send_raw(pkt)
        self.on_log(f"[CHAT SENT] [{channel}]: {clean}")

    # Verbs the official client dispatcher handles in `Chat.submitMsg`.
    # Each entry maps "how the packet is serialized", not "what it means":
    #  cmd      -> %xt%zm%cmd%1%<verb>%<args>%
    #  local    -> handled in Python (join/reload/afk/rest/goto)
    #  unsupported -> dispatcher exists but the verb is staff/client-only;
    #                 sending a lookalike packet to production would be a guess,
    #                 so it is refused instead (skill: keep unverified ops
    #                 unshippable rather than approximating them).
    _SLASH_CMD_VERBS = frozenset(
        {
            "who", "clear", "bonus", "boost", "frostreset", "queue", "killmap",
            "item", "combat", "modon", "modoff", "adminyell", "iay",
            "getbreakdown", "iteratortest", "size", "getroomname", "getinfo",
            "mod", "pmoff", "pmon", "partyon", "partyoff", "chaton", "chatoff",
            "friendon", "friendoff", "waron", "waroff", "kickall", "restart",
            "restartnow", "shutdown", "shutdownnow", "empty", "whitelist",
            "datadump", "monitor", "resetevents", "resetlogins", "resetgrove",
            "resettimes", "getlogins", "gettimes", "clock", "event", "tfer",
            "roomid", "mute", "ban", "ipmute", "kick", "ipkick", "ipunmute",
            "unmute", "freeze", "unfreeze", "watch", "unwatch", "modban",
            "reporthack", "repairavatars", "dynamic", "qv",
        }
    )
    # Moderation/server verbs the dispatcher accepts but a farming bot must
    # never emit: each one mutates other players' sessions or the world
    # (`Chat.as:1782-1985`). Refused before any packet is built.
    _SLASH_STAFF_VERBS = frozenset(
        {
            "mute", "ban", "ipmute", "unmute", "ipunmute", "kick", "ipkick",
            "freeze", "unfreeze", "watch", "unwatch", "modban", "kickall",
            "restart", "restartnow", "shutdown", "shutdownnow", "empty",
            "whitelist", "resetevents", "resetlogins", "resetgrove",
            "resettimes", "getlogins", "gettimes", "clock", "repairavatars",
            "adminyell", "iay", "getbreakdown", "iteratortest", "datadump",
            "monitor", "geta", "seta", "queststring",
        }
    )

    # Argument grammar per `cmd` verb, read from `Chat.submitMsg`
    # (Chat.as:1318-2143): "joined" merges the words into one field
    # (`params.slice(1).join(" ")`), "split" emits every word as its own
    # field. The flag marks verbs the client only serializes with an
    # argument, so a bare verb is refused locally instead of sent as a
    # half-empty packet.
    _SLASH_CMD_GRAMMAR: dict[str, tuple[str, bool]] = {
        "who": ("joined", False),
        "getinfo": ("joined", True),
        "item": ("split", True),
        "combat": ("split", False),
        "event": ("split", True),
        "killmap": ("split", True),
        "getroomname": ("split", True),
        "modon": ("split", False),
        "modoff": ("split", False),
        "queue": ("split", False),
        "frostreset": ("split", False),
        "clear": ("split", True),
        "bonus": ("split", True),
        "boost": ("split", True),
        "addrep": ("split", True),
        "addxp": ("split", True),
        "addv": ("split", True),
        "hp": ("split", True),
        "level": ("split", True),
        "getevents": ("split", True),
        "getevent": ("split", True),
        "mod": ("split", False),
        "pmoff": ("split", False),
        "pmon": ("split", False),
        "partyon": ("split", False),
        "partyoff": ("split", False),
        "chaton": ("split", False),
        "chatoff": ("split", False),
        "friendon": ("split", False),
        "friendoff": ("split", False),
        "waron": ("split", False),
        "waroff": ("split", False),
        "roll": ("split", False),
        "dynamic": ("split", False),
        "tfer": ("split", True),
    }

    _SLASH_LOCAL_VERBS = frozenset(
        {"join", "reload", "afk", "rest", "goto", "pull", "house"}
    )
    _SLASH_UNSUPPORTED_VERBS = frozenset(
        {
            "captest", "multi", "cell", "shop", "sound", "ignore", "unignore",
            "ignoreclear", "report", "reportlang", "debug", "geta", "seta",
            "queststring", "yuki", "guild", "guildreset",
            "guildremove", "gr", "guildPromote", "gp", "guildDemote", "gd",
            "motd", "gc", "guildcreate", "renameGuild", "rg", "ginv",
            "pi", "pk", "duel", "friends", "addquest",
            "removequest", "forcestart", "forcestop", "fps", "roll",
        }
    )

    _SLASH_EMOTE_VERBS = frozenset(
        {
            "dance", "laugh", "lol", "point", "use", "fart", "backflip", "sleep",
            "jump", "punt", "dance2", "swordplay", "feign", "wave", "bow", "cry",
            "unsheath", "cheer", "stern", "salute", "airguitar", "facepalm",
            "samba", "danceweapon", "useweapon", "powerup", "kneel", "jumpcheer",
            "salute2", "cry2", "spar", "stepdance", "headbang", "dazed",
        }
    )
    # Client-side rename: Chat.submitMsg maps `lol` onto the `laugh` animation
    # before serializing (Chat.as:2117-2120).
    _EMOTE_ALIASES = {"lol": "laugh"}

    def chat(self, message: str, channel: str = "zone") -> None:
        """Kirim chat, atau eksekusi slash command seperti client AQW."""
        if self.state != BotState.IN_MAP:
            raise BotError(f"tidak bisa chat saat bot berstatus {self.state.value}")
        clean = message.replace("%", "").strip()
        if not clean:
            return

        # Slash command tidak boleh dikirim sebagai bubble chat. Grammar and
        # routing follow `Chat.submitMsg` (Chat.as:1318-2163).
        if clean.startswith("/"):
            parts = clean[1:].split()
            command = parts[0].lower()
            argument = " ".join(parts[1:]).strip()
            if command == "join":
                if not argument:
                    raise BotError("pemakaian: /join <map>, contoh: /join yulgar-14045")
                self.join_map(argument)
                return
            if command == "goto":
                if not argument:
                    raise BotError("pemakaian: /goto <nama pemain>")
                self._goto_player(argument)
                return
            if command == "pull":
                if not argument:
                    raise BotError("pemakaian: /pull <nama pemain>")
                # World.pull lower-cases the whole target (World.as:12351).
                target = " ".join(argument.lower().split())
                self._send_raw(sfs.slash_command_packet("pull", [target], room=1))
                self.on_log(f"[PULL] minta server menarik {target}")
                return
            if command == "reload":
                self.reload()
                return
            if command == "afk":
                self.set_afk(not self.is_afk)
                return
            if command == "rest":
                self._send_raw(sfs.rest_packet())
                self.on_log("[REST] mulainya istirahat (emotea rest)")
                return
            if command == "house":
                # `World.gotoHouse` — own house when no argument is given.
                target = argument or self.username
                self._send_raw(sfs.house_packet(target, room=1))
                self.on_log(f"[HOUSE] masuk rumah {target}")
                return
            if command == "invite":
                if not argument:
                    raise BotError("pemakaian: /invite <nama pemain>")
                self._send_raw(sfs.party_invite_packet(argument, room=1))
                self.on_log(f"[PARTY] undang {argument}")
                return
            if command == "ps":
                if not argument:
                    raise BotError("pemakaian: /ps <nama pemain>")
                self._send_raw(sfs.party_summon_packet(argument, room=1))
                self.on_log(f"[PARTY] summon {argument}")
                return
            if command == "friend":
                if not argument:
                    raise BotError("pemakaian: /friend <nama pemain>")
                self._send_raw(sfs.friend_request_packet(argument, room=1))
                self.on_log(f"[FRIEND] minta pertemanan {argument}")
                return
            if command in {"e", "me", "em"}:
                # Third-person emote (Chat.as:2018-2033): emotes go to the
                # `em` channel with the current room, not `message`.
                if not argument:
                    raise BotError(f"pemakaian: /{command} <teks emote>")
                self._send_raw(sfs.em_packet(self.room_id, argument))
                self.on_log(f"[EMOTE] {argument}")
                return
            if command in {"pk", "partykick"}:
                if not argument:
                    raise BotError("pemakaian: /pk <nama pemain>")
                self._send_raw(sfs.party_kick_packet(argument, room=1))
                self.on_log(f"[PARTY] kick {argument}")
                return
            if command == "duel":
                if not argument:
                    raise BotError("pemakaian: /duel <nama pemain>")
                self._send_raw(sfs.duel_invite_packet(argument, room=1))
                self.on_log(f"[DUEL] tantang {argument}")
                return
            if command in {"gi", "guildInvite"}:
                if not argument:
                    raise BotError("pemakaian: /gi <nama pemain>")
                self._send_raw(sfs.guild_invite_packet(argument, room=1))
                self.on_log(f"[GUILD] undang {argument}")
                return
            if command in self._SLASH_EMOTE_VERBS:
                # Chat.as emote branch: cmd becomes the `emotea` extension and
                # only the emote name is serialized (Chat.as:2114-2122, 2152-2156).
                emote = self._EMOTE_ALIASES.get(command, command)
                self._send_raw(sfs.emote_packet(emote, room=1))
                self.on_log(f"[EMOTE] {emote}")
                return
            if command in self._SLASH_STAFF_VERBS:
                # Dispatcher-only room for staff and moderators; a farming bot
                # has no business emitting these (`Chat.as:1841-1985`).
                raise BotError(
                    f"slash command /{command} ditolak: verb moderasi/staff, "
                    "tidak pernah dikirim oleh bot farming"
                )
            if command == "roomid":
                # The client pushes `roomID`, its own username, then the room
                # argument (`Chat.as:1803-1808`); the old code sent only the
                # argument, so the server never saw the parameter it expected.
                if not argument:
                    raise BotError("pemakaian: /roomid <id room>")
                args = ["roomID", self.username, *argument.split()]
                # Built directly: the client emits the literal camelCase
                # `roomID` (Chat.as:1805), which the generic builder lowercases.
                self._send_raw(sfs.xt_str("zm", "cmd", args, 1))
                self.on_log(f"[CMD] /roomid {argument}")
                return
            if command in self._SLASH_CMD_GRAMMAR:
                # Shape the packet exactly as `Chat.submitMsg` does per verb:
                # some verbs join the words into one field, others emit each
                # word separately, and a few need at least one argument
                # (Chat.as:1318-2143).
                mode, requires_argument = self._SLASH_CMD_GRAMMAR[command]
                words = argument.split()
                if requires_argument and not words:
                    raise BotError(f"pemakaian: /{command} <argumen>")
                if mode == "joined":
                    args = [argument] if argument else []
                else:
                    args = words
                self._send_raw(sfs.slash_command_packet(command, args, room=1))
                self.on_log(f"[CMD] /{command}{(' ' + argument) if argument else ''}")
                return
            if command in self._SLASH_LOCAL_VERBS:
                # Client-side only (`cmd = null` in the dispatcher): the client
                # acts locally and never emits this verb. Refuse rather than
                # send a packet the live server has no reason to accept.
                raise BotError(
                    f"slash command /{command} hanya berjalan di client, "
                    "tidak dikirim ke server"
                )
            if command in self._SLASH_UNSUPPORTED_VERBS:
                raise BotError(
                    f"slash command /{command} belum didukung: butuh hak akses "
                    "staff atau alur client (cell/shop/guild) yang belum "
                    "diverifikasi untuk headless"
                )
            raise BotError(f"slash command tidak didukung: /{command}")

        pkt = sfs.chat_packet(self.room_id, clean, channel=channel)
        self._send_raw(pkt)
        self.on_log(f"[CHAT SENT] [{channel}]: {clean}")

    def _goto_player(self, argument: str) -> None:
        """`/goto` exactly like ``World.goto`` (World.as:12323-12349).

        The client has two branches: when the target is already in the local
        area tree it walks to that cell with ``moveToCell`` and never sends
        ``cmd goto``; only a target outside the area falls back to
        ``sendXtMessage('zm','cmd',['goto',name],'str',1)``. Always using the
        ``cmd`` form was why a same-area ``/goto`` looked dead: the server only
        honors it for a player it must summon, and the client had already moved
        locally without any packet.
        """
        target = " ".join(argument.lower().split())
        if not target:
            raise BotError("pemakaian: /goto <nama pemain>")
        me = self._area_players.get(self.username.lower())
        other = self._area_players.get(target)
        # World.goto only gates on the caller's state; the target may lack a
        # state while its data is still loading. MoveToCell when we have both
        # cells and they differ (World.as:12330-12342).
        if (
            other is not None
            and me is not None
            and (me[2] or 0) == 1
            and other[0]
            and me[0]
            and other[0] != me[0]
        ):
            cell, pad = other[0], other[1]
            self._send_raw(
                sfs.move_to_cell_packet(room=self.room_id, cell=cell, pad=pad or "Spawn")
            )
            self.on_log(f"[GOTO] pindah ke cell {cell}/{pad or 'Spawn'} ({target})")
            return
        self._send_raw(sfs.goto_player_packet(target, room=1))
        self.on_log(f"[GOTO] minta server menuju {argument}")

    def join_map(self, map_name: str) -> None:
        """Pindah ke map/room seperti perintah game ``/join``."""
        if self.state != BotState.IN_MAP:
            raise BotError(f"tidak bisa join saat bot berstatus {self.state.value}")
        target = map_name.strip()
        if not target:
            raise BotError("nama map tidak boleh kosong")
        self.on_log(f"[JOIN] menuju {target}...")
        self._set_state(BotState.JOINING_MAP)
        try:
            self.room_id = self._join_map_and_wait(target)
            self.target_map = target
            self._set_state(BotState.IN_MAP)
            self.on_log(f"[JOIN] berhasil: {self.current_map} (room #{self.room_id})")
        except Exception:
            self._set_state(BotState.IN_MAP)
            raise

    def set_afk(self, enable: bool = True) -> None:
        """Kirim toggle status AFK (World.afkToggle pakai channel `afk`)."""
        if self.state != BotState.IN_MAP:
            return
        pkt = sfs.afk_packet(enable=enable)
        self._send_raw(pkt)
        self.is_afk = enable
        self.on_log(f"[AFK] status -> {'AFK' if enable else 'ACTIVE'}")

    def move(self, x: int, y: int, speed: int = 10) -> None:
        """Gerakkan karakter ke koordinat (x, y) di map saat ini.

        ``speed`` = kecepatan berjalan (default 10, lari 14). Menggunakan
        ``curRoom`` / room id yang aktif, sesuai paket yang dikirim client.
        """
        if self.state != BotState.IN_MAP:
            raise BotError(f"tidak bisa move saat bot berstatus {self.state.value}")
        pkt = sfs.move_packet(room=self.room_id, x=x, y=y, speed=speed)
        self._send_raw(pkt)
        self.on_log(f"[MOVE] -> x={x}, y={y} (speed {speed}, room #{self.room_id})")

    def reload(self) -> None:
        """Reload map saat ini (/join kembali ke target_map)."""
        if self.state != BotState.IN_MAP:
            raise BotError("bot belum di dalam map")
        self.on_log(f"[ACTION] reloading map {self.target_map}...")
        self.room_id = self._join_map_and_wait(self.target_map)
        time.sleep(0.1)
        self.set_afk(True)

    def logout(self) -> None:
        """Kirim logout dan stop."""
        self.on_log("[ACTION] logout dipanggil user")
        self.stop()
