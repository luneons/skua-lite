"""Klien protokol SmartFoxServer (SFS) untuk AQW.

Format wire terverifikasi dari `SmartFoxClient.as` (decompile Game.swf):
  * setiap paket diakhiri satu null byte (0x00)
  * XML : ``<msg t='sys'><body action='X' r='R'>BODY</body></msg>``
  * STR : ``%xt%{name}%{cmd}%{room}%{arg}%{arg}%...%``
  * pesan tipe "str" dikirim via ``sendString`` (tanpa header XML)
"""
from __future__ import annotations

import json
import re

from . import config

MSG_XML = "<"
MSG_STR = "%"


# --------------------------------------------------------------------------
# Framing
# --------------------------------------------------------------------------
class PacketFramer:
    """Memecah stream byte menjadi paket-paket yang dipisah null byte.

    Menangani paket yang terpotong antar-chunk (termasuk karakter UTF-8
    yang terbelah dua read).
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[str]:
        self._buf.extend(chunk)
        out: list[str] = []
        while True:
            idx = self._buf.find(b"\x00")
            if idx == -1:
                break
            raw = bytes(self._buf[:idx])
            del self._buf[: idx + 1]
            if raw:
                out.append(raw.decode("utf-8", errors="replace"))
        return out


def build_packet(text: str) -> bytes:
    """Bungkus payload teks menjadi paket wire (ditutup null byte)."""
    return text.encode("utf-8") + b"\x00"


# --------------------------------------------------------------------------
# Paket XML (sistem / SmartFox)
# --------------------------------------------------------------------------
def _make_xml_header(attrs: dict[str, str]) -> str:
    parts = "<msg"
    for k, v in attrs.items():
        parts += f" {k}='{v}'"
    return parts + ">"


def _xml_packet(attrs: dict[str, str], action: str, room: int, body: str) -> bytes:
    header = _make_xml_header(attrs)
    full = f"{header}<body action='{action}' r='{room}'>{body}</body></msg>"
    return build_packet(full)


def verchk_packet() -> bytes:
    """Handshake awal: verChk."""
    body = f"<ver v='{config.SFS_VERSION}' />"
    return _xml_packet({"t": "sys"}, "verChk", 0, body)


def login_packet(nick: str, pword: str, zone: str | None = None) -> bytes:
    """Paket login zone_master.

    nick  = ``{clientToken}~{username}~{clientVersion}``
    pword = ``objLogin.sToken`` dari HTTP login
    """
    zone = zone or config.LOGIN_ZONE
    body = (
        f"<login z='{zone}'>"
        f"<nick><![CDATA[{nick}]]></nick>"
        f"<pword><![CDATA[{pword}]]></pword>"
        "</login>"
    )
    return _xml_packet({"t": "sys"}, "login", 0, body)


# --------------------------------------------------------------------------
# Paket STR (extension / game)
# --------------------------------------------------------------------------
def xt_str(name: str, cmd: str, args: list[str], room: int) -> bytes:
    """Bentuk kanonik paket xt tipe 'str'."""
    parts = [MSG_STR, "xt", MSG_STR, name, MSG_STR, cmd, MSG_STR, str(room), MSG_STR]
    text = "".join(parts)
    for a in args:
        text += ("" if a is None else str(a)) + MSG_STR
    return build_packet(text)


def join_packet(username: str, map_name: str, room: int = 1) -> bytes:
    """Paket pindah map (sama seperti ``/join`` di client).

    Format wire terverifikasi dari capture server AQW:
    ``%xt%zm%cmd%1%tfer%<username>%<map-room>%``

    Catatan: client mengirim room ``1`` (bukan room area saat ini) dan
    TIDAK menyertakan cell/pad, berbeda dari tebakan awal.
    """
    return xt_str("zm", "cmd", ["tfer", username, map_name], room)


def goto_player_packet(username: str, room: int = 1) -> bytes:
    """Request `/goto <player>` when the player is not in local ``uoTree``.

    Anchored to ``World.goto``: ``sendXtMessage('zm','cmd',['goto',name],
    'str',1)``. The official client lower-cases the target first.
    """
    target = " ".join(str(username).strip().lower().split())
    if not target:
        raise ValueError("username goto tidak boleh kosong")
    return xt_str("zm", "cmd", ["goto", target], room)


def slash_command_packet(command: str, args: list[str] | tuple[str, ...] = (), room: int = 1) -> bytes:
    """Serialize a slash command through AQW's ``cmd`` extension channel."""
    verb = str(command).strip().lstrip("/").lower()
    if not verb:
        raise ValueError("slash command tidak boleh kosong")
    clean_args = [str(value).strip() for value in args if str(value).strip()]
    return xt_str("zm", "cmd", [verb, *clean_args], room)


def move_to_cell_packet(room: int, cell: str, pad: str = "Spawn") -> bytes:
    """Move within an area exactly like ``World.moveToCell``."""
    target_cell = str(cell).strip()
    target_pad = str(pad).strip() or "Spawn"
    if not target_cell:
        raise ValueError("cell tidak boleh kosong")
    return xt_str("zm", "moveToCell", [target_cell, target_pad], int(room))


def em_packet(room: int, text: str) -> bytes:
    """Third-person emote (`Chat.submitMsg`: channel ``em``).

    Anchored to `Chat.as:2018-2033`: `cmd='em'`, first field the cleaned
    text, second field `chn.event.str` (`"event"`), envelope room the
    current channel room.
    """
    body = str(text).strip()
    if not body:
        raise ValueError("emote /me tidak boleh kosong")
    return xt_str("zm", "em", [body, "event"], int(room))


def party_kick_packet(username: str, room: int = 1) -> bytes:
    """Party kick (`World.partyKick`: channel ``gp``, arg ``pk``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username party kick tidak boleh kosong")
    return xt_str("zm", "gp", ["pk", name], room)


def duel_invite_packet(username: str, room: int = 1) -> bytes:
    """Duel invite (`World.sendDuelInvite`: channel ``duel``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username duel tidak boleh kosong")
    return xt_str("zm", "duel", [name], room)


def chat_packet(room: int, message: str, channel: str = "zone") -> bytes:
    """Paket chat: ``%xt%zm%message%{room}%{msg}%{channel}%``."""
    return xt_str("zm", "message", [message, channel], room)


def afk_packet(enable: bool = True) -> bytes:
    """Toggle AFK.

    Anchored to ``World.afkToggle``: ``sendXtMessage('zm','afk',[!afk],
    'str',1)`` — the extension name is ``afk`` and the room is always ``1``,
    not the ``cmd`` channel and not the area room.
    """
    return xt_str("zm", "afk", ["true" if enable else "false"], 1)


def emote_packet(emote: str, room: int = 1) -> bytes:
    """Play an emote exactly like ``World.rest``/``Chat`` emote branch.

    Anchored to ``World.rest`` (``sendXtMessage('zm','emotea',['rest'],
    'str',1)``) and ``Chat.submitMsg`` (``cmd='emotea'`` with the emote name).
    """
    value = str(emote).strip().lower()
    if not value:
        raise ValueError("emote tidak boleh kosong")
    return xt_str("zm", "emotea", [value], room)


def rest_request_packet() -> bytes:
    """Repeat rest while already seated (``World.restRequest``)."""
    return xt_str("zm", "restRequest", [""], 1)


def house_packet(username: str, room: int = 1) -> bytes:
    """Enter a player's house (`World.gotoHouse`: channel ``house``).

    The client lower-cases the target and sends it on channel ``house`` with
    room ``1`` — not on ``cmd``.
    """
    target = " ".join(str(username).strip().lower().split())
    if not target:
        raise ValueError("username house tidak boleh kosong")
    return xt_str("zm", "house", [target], room)


def party_invite_packet(username: str, room: int = 1) -> bytes:
    """Party invite (`World.partyInvite`: channel ``gp``, arg ``pi``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username party invite tidak boleh kosong")
    return xt_str("zm", "gp", ["pi", name], room)


def party_summon_packet(username: str, room: int = 1) -> bytes:
    """Party summon (`World.partySummon`: channel ``gp``, arg ``ps``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username party summon tidak boleh kosong")
    return xt_str("zm", "gp", ["ps", name], room)


def friend_request_packet(username: str, room: int = 1) -> bytes:
    """Friend request (`World.requestFriend`: channel ``requestFriend``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username friend tidak boleh kosong")
    return xt_str("zm", "requestFriend", [name], room)


def guild_invite_packet(username: str, room: int = 1) -> bytes:
    """Guild invite (`World.guildInvite`: channel ``guild``, arg ``gi``)."""
    name = str(username).strip()
    if not name:
        raise ValueError("username guild invite tidak boleh kosong")
    return xt_str("zm", "guild", ["gi", name], room)


def move_packet(room: int, x: int, y: int, speed: int = 10) -> bytes:
    """Paket gerak karakter (sama seperti jalan di client).

    Format wire terverifikasi dari ``World.as``:
    ``sendXtMessage("zm","mv",[x,y,speed],"str",curRoom)`` ->
    ``%xt%zm%mv%<room>%<x>%<y>%<speed>%``.

    ``speed`` default 10 (kecepatan jalan normal). Pakai 14 untuk lari.
    """
    return xt_str("zm", "mv", [int(x), int(y), int(speed)], room)


def retrieve_inventory_packet(room: int, user_id: int) -> bytes:
    """Minta inventory karakter; wajib sebelum server menerima tfer.

    Format berasal dari ``World.getInventory``:
    ``sendXtMessage('zm','retrieveInventory',[uid],'str',curRoom)``.
    """
    return xt_str("zm", "retrieveInventory", [int(user_id)], room)


def retrieve_user_data_packet(room: int, user_id: int) -> bytes:
    """Request avatar data as emitted by World.getUserDataById."""
    return xt_str("zm", "retrieveUserData", [int(user_id)], room)


def get_drop_packet(room: int, drop_id: int) -> bytes:
    """Ambil satu drop berdasarkan drop ID server."""
    return xt_str("zm", "getDrop", [int(drop_id)], room)


def rest_packet() -> bytes:
    """Sit down and start resting (``World.rest`` -> ``emotea rest``).

    The old ``cmd restRequest`` form was wrong: ``rest`` in ``Chat.submitMsg``
    routes to ``World.rest``, which sends the ``emotea`` extension. Repeat
    rest while seated uses :func:`rest_request_packet`.
    """
    return emote_packet("rest")


def res_player_timed_packet(user_id: int, room: int = 1) -> bytes:
    """Respawn player after death (World.resPlayer call site: World_as 4776-4780).

    The wire room follows World.curRoom: every other action call site passes
    ``curRoom``, so the current area room (``bot.room_id``) is used here too.
    """
    uid = int(user_id)
    if uid <= 0:
        raise ValueError("user_id harus positif")
    return xt_str("zm", "resPlayerTimed", [uid], room)


def use_item_packet(room: int, item_id: int) -> bytes:
    """Gunakan consumable/booster berdasarkan item ID."""
    return xt_str("zm", "serverUseItem", ["+", int(item_id)], room)


def sell_item_packet(
    room: int, item_id: int, quantity: int, char_item_id: int
) -> bytes:
    """Jual item inventory memakai format paket Skua terverifikasi."""
    return xt_str(
        "zm", "sellItem", [int(item_id), int(quantity), int(char_item_id)], room
    )


def load_bank_packet(room: int) -> bytes:
    """Minta seluruh isi bank."""
    return xt_str("zm", "loadBank", ["All"], room)


def equip_item_packet(room: int, item_id: int) -> bytes:
    """Minta equip satu item memakai perintah equipItem milik server.

    Skua memfilter inbound logger untuk ``p[2] == "equipItem"``, jadi nama
    perintah sudah terbukti di wire server; responsnya terverifikasi dari
    perubahan ``bEquip`` pada inventory berikutnya.
    """
    return xt_str("zm", "equipItem", [int(item_id)], room)


def bank_to_inventory_packet(room: int, item_id: int, char_item_id: int) -> bytes:
    """Pindahkan satu item bank ke inventory."""
    return xt_str("zm", "bankToInv", [int(item_id), int(char_item_id)], room)


def bank_from_inventory_packet(room: int, item_id: int, char_item_id: int) -> bytes:
    """Pindahkan satu item inventory ke bank."""
    return xt_str("zm", "bankFromInv", [int(item_id), int(char_item_id)], room)


def bank_swap_packet(
    room: int,
    inv_id: int,
    inv_char_id: int,
    bank_id: int,
    bank_char_id: int,
) -> bytes:
    """Tukar item inventory dan bank ketika inventory penuh."""
    return xt_str(
        "zm",
        "bankSwapInv",
        [int(inv_id), int(inv_char_id), int(bank_id), int(bank_char_id)],
        room,
    )


def try_quest_complete_packet(
    room: int,
    quest_id: int,
    reward_id: int = -1,
    turn_ins: str = "",
) -> bytes:
    """Kirim turn-in quest memakai wire format Skua 1.4.4."""
    return xt_str(
        "zm",
        "tryQuestComplete",
        [int(quest_id), int(reward_id), "false", turn_ins, "wvz"],
        room,
    )


def aggro_mon_packet(room: int, map_ids: list[int] | tuple[int, ...]) -> bytes:
    """Tarik monster berdasarkan MonMapID yang sudah diketahui."""
    ids = [int(map_id) for map_id in map_ids]
    if not ids:
        raise ValueError("map_ids tidak boleh kosong")
    return xt_str("zm", "aggroMon", ids, room)


def gar_packet(
    room: int,
    action_id: int,
    action_ref: str,
    targets: list[str] | tuple[str, ...],
    *,
    item_id: int | None = None,
) -> bytes:
    """Serialize one combat action exactly as ``World.getActionResult``.

    ``action_id`` is the rolling 0..30 client sequence. Targets use the
    reference-client forms ``m:<MonMapID>`` and ``p:<uid>``. Consumable slot
    ``i1`` carries its assigned item ID as one extra argument.
    """
    if action_ref not in {"aa", "a1", "a2", "a3", "a4", "i1"}:
        raise ValueError(f"action_ref tidak didukung: {action_ref!r}")
    if not 0 <= int(action_id) <= 30:
        raise ValueError("action_id harus 0..30")
    clean_targets: list[str] = []
    for target in targets:
        if not re.fullmatch(r"[mp]:[1-9]\d*", str(target)):
            raise ValueError(f"target combat tidak valid: {target!r}")
        clean_targets.append(str(target))
    if not clean_targets:
        raise ValueError("targets tidak boleh kosong")
    target_arg = ",".join(f"{action_ref}>{target}" for target in clean_targets)
    args: list[object] = [int(action_id), target_arg]
    if action_ref == "i1":
        if item_id is None or int(item_id) <= 0:
            raise ValueError("i1 membutuhkan item_id positif")
        args.append(int(item_id))
    elif item_id is not None:
        raise ValueError("item_id hanya berlaku untuk i1")
    args.append("wvz")
    # Game.as emits GAR with envelope room 1, regardless of current area.
    return xt_str("zm", "gar", args, room=room)


def logout_packet(room: int = -1) -> bytes:
    """Paket logout SFS."""
    return _xml_packet({"t": "sys"}, "logout", room, "")


def get_room_list_packet(room: int = -1) -> bytes:
    """Paket sys getRmList (dikirim client setelah logOK)."""
    return _xml_packet({"t": "sys"}, "getRmList", room, "")


def round_trip_packet(room: int = 1) -> bytes:
    """Paket sys roundTrip (keep-alive / ping latency)."""
    return _xml_packet({"t": "sys"}, "roundTrip", room, "")


# --------------------------------------------------------------------------
# Parser balasan server
# --------------------------------------------------------------------------
def parse_str_packet(text: str) -> dict | None:
    """Parse paket '%' menjadi dict {name, cmd, room, args}.

    Mengembalikan None bila bukan paket xt bertipe str.
    """
    if not text.startswith(MSG_STR):
        return None
    parts = text.split(MSG_STR)
    # parts[0] == "" karena leading '%'
    # ['', 'xt', name, cmd, room, arg, arg, ..., '']
    if len(parts) < 5 or parts[1] != "xt":
        return None
    name = parts[2]
    cmd = parts[3]
    try:
        room = int(parts[4])
    except (ValueError, IndexError):
        room = -1
    # bagian ekor kosong akibat trailing '%'
    tail = parts[5:]
    if tail and tail[-1] == "":
        tail = tail[:-1]
    return {"name": name, "cmd": cmd, "room": room, "args": tail}


def parse_uotls(text: str) -> dict | None:
    """Parse `%xt%uotls%-1%<username>%k:v,k:v%` player-field updates.

    AQW routes another player's movement/cell change through this packet
    (``Game.as:1411-1420`` builds the field map, ``userTreeWrite`` at 5377+
    converts ``tx``/``ty``/``sp`` to int). Outbound mirrors use ``mv``
    (``World.as:3491``) and ``moveToCell`` (``World.as:2884``).
    """
    parts = text.split(MSG_STR)
    if len(parts) < 6 or parts[1:3] != ["xt", "uotls"]:
        return None
    username = parts[4]
    if not username:
        return None
    fields: dict[str, object] = {}
    for chunk in parts[5].split(","):
        key, sep, value = chunk.partition(":")
        if not sep or not key:
            continue
        if key.lower() in {"tx", "ty", "sp"} or key.lower().startswith("int"):
            try:
                fields[key] = int(value)
            except (ValueError, TypeError):
                fields[key] = None
        else:
            fields[key] = value
    return {"username": username, "fields": fields}


def parse_chat_message(text: str) -> dict | None:
    """Parse AQW chatm packet into channel/message/sender metadata.

    Wire args follow Game.as: channel~message, username, uid, room id, flags.
    """
    parts = text.split(MSG_STR)
    # ['', 'xt', 'chatm', '-1', 'channel~message', 'sender', uid, room, ...]
    if len(parts) < 8 or parts[1:3] != ["xt", "chatm"]:
        return None
    channel_message = parts[4]
    channel, separator, message = channel_message.partition("~")
    if not separator:
        return None
    try:
        user_id = int(parts[6])
        room = int(parts[7])
    except (ValueError, TypeError):
        return None
    return {
        "channel": channel,
        "message": message,
        "sender": parts[5],
        "user_id": user_id,
        "room": room,
    }


def parse_exit_area(text: str) -> dict | None:
    """Parse %xt%exitArea%-1%<uid>%<username>% so owner departure is detected."""
    parts = text.split(MSG_STR)
    if len(parts) < 6 or parts[1:3] != ["xt", "exitArea"]:
        return None
    try:
        user_id = int(parts[4])
    except (ValueError, TypeError):
        return None
    return {"user_id": user_id, "username": parts[5]}


_XML_ATTR_RE = re.compile(r"([\w]+)=['\"]([^'\"]*)['\"]")


def _xml_attrs(fragment: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _XML_ATTR_RE.findall(fragment)}


def parse_user_enter_room(text: str) -> dict | None:
    """Parse SFS XML user-enter-room notification (uER)."""
    match = re.search(
        r"<body\b([^>]*)>(.*?)</body>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match or not re.search(
        r"\baction=['\"]uER['\"]", match.group(1), re.IGNORECASE
    ):
        return None
    attrs = _xml_attrs(match.group(1))
    user_match = re.search(r"<u\b([^>]*)>(.*?)</u>|<u\b([^>]*)/>", match.group(2), flags=re.IGNORECASE | re.DOTALL)
    if not user_match:
        return None
    user_attr_fragment = user_match.group(1) or user_match.group(3) or ""
    user_attrs = _xml_attrs(user_attr_fragment)
    user_body = user_match.group(2) or ""
    username = user_attrs.get("n")
    if not username:
        name_match = re.search(r"<n>(.*?)</n>", user_body, flags=re.IGNORECASE | re.DOTALL)
        username = name_match.group(1).strip() if name_match else None
    if username:
        cdata_match = re.fullmatch(r"<!\[CDATA\[(.*?)\]\]>", username, flags=re.DOTALL)
        if cdata_match:
            username = cdata_match.group(1).strip()
    try:
        return {
            "room": int(attrs.get("r", "-1")),
            "user_id": int(user_attrs.get("i") or user_attrs["id"]),
            "username": username or "",
        }
    except (KeyError, ValueError):
        return None


def parse_user_gone(text: str) -> dict | None:
    """Parse SFS userGone room departure event."""
    match = re.search(
        r"<body\b([^>]*)>(.*?)</body>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match or not re.search(
        r"\baction=['\"]userGone['\"]", match.group(1), re.IGNORECASE
    ):
        return None
    attrs = _xml_attrs(match.group(1))
    user_match = re.search(r"<user\b([^>]*)/?>", match.group(2), flags=re.IGNORECASE)
    if not user_match:
        return None
    user_attrs = _xml_attrs(user_match.group(1))
    try:
        return {"room": int(attrs.get("r", "-1")), "user_id": int(user_attrs["id"])}
    except (KeyError, ValueError):
        return None


def parse_init_user_data(text: str) -> dict | None:
    """Parse target's user-data response; this confirms actual avatar arrival."""
    parsed = parse_xt_json(text)
    if parsed is None or parsed.get("cmd") != "initUserData":
        return None
    obj = parsed["obj"]
    try:
        user_id = int(obj["uid"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"room": parsed["room"], "user_id": user_id}


def parse_retrieve_user_data(text: str) -> dict | None:
    """Parse the game's retrieveUserData presence request carrying a user id."""
    parsed = parse_str_packet(text)
    if parsed is None or parsed.get("name") != "zm" or parsed.get("cmd") != "retrieveUserData":
        return None
    args = parsed.get("args", [])
    if not args:
        return None
    try:
        user_id = int(args[0])
    except (ValueError, TypeError):
        return None
    return {"room": parsed["room"], "user_id": user_id}


def parse_login_user_id(text: str) -> int | None:
    """Ambil user id sesi dari paket ``loginResponse``.

    Format nyata: ``%xt%loginResponse%-1%true%<uid>%<username>%...%``.
    """
    parts = text.split(MSG_STR)
    # ['', 'xt', 'loginResponse', '-1', 'true', '<uid>', ...]
    if len(parts) < 6 or parts[1:3] != ["xt", "loginResponse"]:
        return None
    if parts[4].lower() != "true":
        return None
    try:
        return int(parts[5])
    except (ValueError, TypeError):
        return None


def parse_xt_json(text: str) -> dict | None:
    """Parse paket xt bertipe JSON.

    AQW mengirim sebagian aksi game sebagai JSON, bukan XML, misalnya:
    ``{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,
    "areaName":"battleon-1",...}}}``

    Mengembalikan dict ``{"cmd":..., "room":..., "obj":...}`` atau None.
    """
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if data.get("t") != "xt":
        return None
    body = data.get("b") or {}
    obj = body.get("o") or {}
    if not isinstance(obj, dict):
        return None
    try:
        room = int(body.get("r", -1))
    except (ValueError, TypeError):
        room = -1
    return {"cmd": obj.get("cmd"), "room": room, "obj": obj}


def parse_move_to_area(text: str) -> tuple[str, int] | None:
    """Ambil (areaName, roomId) dari paket moveToArea.

    ``areaName`` berformat ``"<map>-<room>"``, mis. ``"battleon-1"``.
    ``roomId`` adalah id area di world (dipakai saat mengirim tfer).
    """
    parsed = parse_xt_json(text)
    if parsed is None or parsed.get("cmd") != "moveToArea":
        return None
    obj = parsed["obj"]
    name = obj.get("areaName") or obj.get("strMapName") or ""
    try:
        room_id = int(obj.get("areaId", parsed["room"]))
    except (ValueError, TypeError):
        room_id = parsed["room"]
    if not name:
        return None
    return str(name), room_id


def parse_room_id(text: str) -> int | None:
    """Ambil room id dari balasan joinOK: ``action='joinOK' r='1'``."""
    marker = "r='"
    for key in ("joinOK", "join"):
        pos = text.find(key)
        if pos == -1:
            continue
        idx = text.find(marker, pos)
        if idx == -1:
            continue
        start = idx + len(marker)
        end = text.find("'", start)
        if end == -1:
            continue
        try:
            return int(text[start:end])
        except ValueError:
            return None
    # fallback: cari r='N' pertama
    idx = text.find(marker)
    if idx != -1:
        start = idx + len(marker)
        end = text.find("'", start)
        try:
            return int(text[start:end])
        except (ValueError, TypeError):
            return None
    return None
