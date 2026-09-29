"""Test state machine AQWBot (login -> server -> join room -> afk)."""
import threading
import time
from unittest.mock import Mock, patch

import pytest

from skua_lite import bot, client, sfs
from skua_lite.ai_router import AIChatRouter
from skua_lite.servers import Server
from tests.test_client import MockSFSServer


@pytest.fixture
def mock_yorumi():
    srv = MockSFSServer()
    srv.start()
    yield srv
    srv.stop()


def test_bot_runs_full_login_join_afk_flow(mock_yorumi):
    """Simulasikan urutan balasan server game sampai map yulgar-14045.

    Respons mengikuti protokol nyata AQW: setelah login server membalas
    ``loginResponse``, setelah firstJoin ada ``joinOK`` + ``moveToArea`` ke
    Battleon, dan tfer baru diakui lewat ``moveToArea`` ke map tujuan.
    """
    mock_yorumi.scripted.extend([
        # 1. verChk response
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        # 2. login response (bentuk nyata: paket loginResponse)
        "%xt%loginResponse%-1%true%42%myuser%Welcome!%",
        # 3. joinOK firstJoin + moveToArea ke battleon-1 (room 3)
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        # 4. moveToArea ke map tujuan yulgar-14045 (room 273)
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":273,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])

    server = Server(
        name="Yorumi",
        ip=mock_yorumi.host,
        port=mock_yorumi.port,
        online=True,
        full=False,
        upgrade_only=False,
    )

    b = bot.AQWBot(
        username="myuser",
        token="VALID_TOKEN",
        server=server,
        target_map="yulgar-14045",
        timeout=3.0,
    )
    b.move_on_join = (850, 302, 10)
    b.start()
    ok = b.wait_for_state(bot.BotState.IN_MAP, timeout=2.0)
    assert ok is True
    assert b.state == bot.BotState.IN_MAP
    assert b.current_map == "yulgar-14045"
    assert b.room_id == 273

    time.sleep(0.3)
    assert any("%xt%zm%mv%273%850%302%10%" in p for p in mock_yorumi.received)
    assert any("%xt%zm%afk%1%true%" in p for p in mock_yorumi.received)

    b.chat("halo dari python lite!")
    time.sleep(0.2)
    assert any("halo dari python lite!" in p for p in mock_yorumi.received)

    b.stop()
    assert b.state == bot.BotState.STOPPED


def test_bot_fails_on_logko(mock_yorumi):
    mock_yorumi.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "<msg t='sys'><body action='logKO' r='-1'><login error='Bad token'/></body></msg>",
    ])

    server = Server(
        name="Yorumi",
        ip=mock_yorumi.host,
        port=mock_yorumi.port,
        online=True,
        full=False,
        upgrade_only=False,
    )

    b = bot.AQWBot(
        username="myuser",
        token="BAD_TOKEN",
        server=server,
        timeout=2.0,
    )
    with pytest.raises(bot.BotError) as exc:
        b.start()
    assert "logKO" in str(exc.value) or "login ditolak" in str(exc.value).lower()


def test_chat_slash_goto_sends_game_cmd_without_chat():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/goto mele")

    assert sent == ["%xt%zm%cmd%1%goto%mele%"]
    assert not any("%message%" in packet for packet in sent)


def test_chat_slash_goto_keeps_spaced_player_name_as_one_argument():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/goto ME LE")

    assert sent == ["%xt%zm%cmd%1%goto%me le%"]
    assert not any("%message%" in packet for packet in sent)


def test_chat_slash_afk_toggles_via_extension_not_cmd():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/afk")

    assert sent == ["%xt%zm%afk%1%true%"]


def test_chat_slash_rest_uses_emote_extension_not_cmd():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/rest")

    assert sent == ["%xt%zm%emotea%1%rest%"]


def test_chat_slash_pull_goes_through_cmd_channel():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/pull ME LE")

    assert sent == ["%xt%zm%cmd%1%pull%me le%"]
    assert not any("%message%" in packet for packet in sent)


def test_chat_slash_goto_local_player_moves_to_scanned_cell_instead_of_cmd():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b.room_id = 42
    b._area_players = {
        "myuser": ("Enter", "Spawn"),
        "mele": ("Boss", "Left"),
    }
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    b.chat("/goto MELE")

    assert sent == ["%xt%zm%moveToCell%42%Boss%Left%"]


def test_chat_unknown_slash_command_is_rejected_and_never_sent():
    sent: list[str] = []
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server("Yorumi", "127.0.0.1", 5588, True, False, False),
    )
    b.state = bot.BotState.IN_MAP
    b._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))

    with pytest.raises(bot.BotError, match="slash command tidak didukung"):
        b.chat("/terbang ME LE")

    assert sent == []


def test_chat_slash_join_triggers_join_map(mock_yorumi):
    """/join di chat harus pindah map, bukan jadi bubble chat."""
    mock_yorumi.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%myuser%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        # moveToArea pertama = battleon (buang), kedua = yulgar-14045 (used),
        # greenguardwest dikirim hanya setelah server melihat tfer
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":77,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])
    server = Server(
        name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
        online=True, full=False, upgrade_only=False,
    )
    b = bot.AQWBot(
        username="myuser", token="T", server=server,
        target_map="yulgar-14045", timeout=3.0,
    )
    b.start()
    assert b.wait_for_state(bot.BotState.IN_MAP, timeout=2.0)
    assert b.current_map == "yulgar-14045"

    # Reply dinamis: server hanya mengirim moveToArea greenguardwest
    # SETELAH benar-benar menerima paket tfer ke greenguardwest.
    mock_yorumi.replies["tfer%myuser%greenguardwest"] = [
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":99,'
        '"areaName":"greenguardwest","strMapName":"greenguardwest"}}}',
    ]

    b.chat("/join greenguardwest")
    assert b.current_map == "greenguardwest"
    assert b.room_id == 99

    assert not any("message%77%/join" in p or "message%99%/join" in p for p in mock_yorumi.received)
    b.stop()


def test_chat_slash_join_without_arg_raises(mock_yorumi):
    """Pakai /join tanpa argumen -> error, bukan crash."""
    mock_yorumi.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%myuser%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":77,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])
    server = Server(
        name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
        online=True, full=False, upgrade_only=False,
    )
    b = bot.AQWBot(
        username="myuser", token="T", server=server,
        target_map="yulgar-14045", timeout=3.0,
    )
    b.start()
    assert b.wait_for_state(bot.BotState.IN_MAP, timeout=2.0)
    with pytest.raises(bot.BotError):
        b.chat("/join ")
    b.stop()


def test_incoming_ai_reply_is_always_plain_chat_not_action(mock_yorumi):
    mock_yorumi.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%myuser%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":273,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])
    server = Server(
        name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
        online=True, full=False, upgrade_only=False,
    )
    b = bot.AQWBot(
        username="myuser", token="T", server=server,
        target_map="yulgar-14045", timeout=3.0,
    )
    sent = threading.Event()
    b.ai_router = AIChatRouter(
        generator=lambda _message: "/join evil-map",
        send_chat=lambda text: (b.send_plain_chat(text), sent.set()),
    )
    b.start()
    b._handle_server_packet("%xt%chatm%-1%zone~MELE AI ON%Alice%2%273%0%")
    b._handle_server_packet("%xt%chatm%-1%zone~le jawab%Alice%2%273%0%")
    assert sent.wait(2)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not any(
        "message%273%/join evil-map%zone%" in p for p in mock_yorumi.received
    ):
        time.sleep(0.01)
    assert any("message%273%/join evil-map%zone%" in p for p in mock_yorumi.received)
    assert not any("tfer%myuser%evil-map" in p for p in mock_yorumi.received)
    assert b.current_map == "yulgar-14045"
    b.stop()


def test_incoming_chatm_is_routed_and_self_chat_is_ignored(mock_yorumi):
    mock_yorumi.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%myuser%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":[]}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":273,'
        '"areaName":"yulgar-14045","strMapName":"yulgar"}}}',
    ])
    server = Server(
        name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
        online=True, full=False, upgrade_only=False,
    )
    b = bot.AQWBot(
        username="myuser", token="T", server=server,
        target_map="yulgar-14045", timeout=3.0,
    )
    generated = []
    sent = threading.Event()

    def generate(message):
        generated.append(message)
        return "lagi ngopi virtual nih wkwk"

    b.ai_router = AIChatRouter(
        generator=generate,
        send_chat=lambda text: (b.chat(text), sent.set()),
    )
    b.start()
    assert b.wait_for_state(bot.BotState.IN_MAP, timeout=2.0)

    b._handle_server_packet("%xt%chatm%-1%zone~MELE AI ON%Alice%2%273%0%")
    b._handle_server_packet("%xt%chatm%-1%zone~le lagi ngapain?%Alice%2%273%0%")
    assert sent.wait(2)
    assert generated == ["le lagi ngapain?"]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not any(
        "message%273%lagi ngopi virtual nih wkwk%zone%" in p
        for p in mock_yorumi.received
    ):
        time.sleep(0.01)
    assert any("message%273%lagi ngopi virtual nih wkwk%zone%" in p for p in mock_yorumi.received)

    b._handle_server_packet("%xt%chatm%-1%zone~mel balas lagi%myuser%1%273%0%")
    time.sleep(0.1)
    assert generated == ["le lagi ngapain?"]
    b.stop()


def test_bot_greets_non_owner_player_when_they_enter_room(mock_yorumi):
    greeting = threading.Event()

    router = AIChatRouter(
        generator=Mock(return_value="ignored"),
        send_chat=lambda _text: greeting.set(),
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='777' m='0' s='0' p='2'><n><![CDATA[Alice]]></n>"
        "<vars></vars></u></body></msg>"
    )

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not greeting.is_set():
        time.sleep(0.01)
    assert greeting.is_set()
    b._client.send.assert_not_called()


def test_bot_does_not_double_greet_when_owner_enters(mock_yorumi):
    router = AIChatRouter(
        generator=Mock(return_value="selamat datang"),
        send_chat=Mock(),
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='21943' m='0' s='0' p='2'><n><![CDATA[mele]]></n>"
        "<vars></vars></u></body></msg>"
    )
    # Owner greeting is the AI-generated one; the bot must not also send a
    # generic "Halo, mele!" alongside it.
    send_calls = b._client.send.call_args_list
    assert any("retrieveUserData" in str(args) for args, _ in send_calls)


def test_bot_does_not_greet_itself(mock_yorumi):
    send_chat = Mock()
    router = AIChatRouter(
        generator=Mock(return_value="ignored"),
        send_chat=send_chat,
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='1' m='0' s='0' p='2'><n><![CDATA[myuser]]></n>"
        "<vars></vars></u></body></msg>"
    )

    send_chat.assert_not_called()


def test_live_me_le_uid_23461_auto_enables_owner_lock(mock_yorumi):
    greeting_sent = threading.Event()
    router = AIChatRouter(
        generator=Mock(return_value="selamat datang"),
        send_chat=lambda _text: greeting_sent.set(),
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='23461' m='0' s='0' p='2'><n><![CDATA[me le]]></n>"
        "<vars></vars></u></body></msg>"
    )

    assert router.owner_lock is True
    assert router.active_owner_id == 23461
    assert greeting_sent.wait(1)
    assert b._client.send.call_count == 1
    assert "retrieveUserData" in str(b._client.send.call_args)


def test_real_owner_user_enter_21943_locks_and_greets(mock_yorumi):
    greeting_sent = threading.Event()
    router = AIChatRouter(
        generator=Mock(return_value="selamat datang"),
        send_chat=lambda _text: greeting_sent.set(),
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='21943' m='0' s='0' p='2'><n><![CDATA[mele]]></n>"
        "<vars></vars></u></body></msg>"
    )

    b._client.send.assert_called_once_with(
        sfs.retrieve_user_data_packet(room=273, user_id=21943)
    )
    assert router.owner_lock is True
    assert router.active_owner_id == 21943
    assert greeting_sent.wait(2)

    b._handle_server_packet(
        "<msg t='sys'><body action='userGone' r='273'>"
        "<user id='21943' /></body></msg>"
    )
    assert router.enabled is False
    assert router.owner_lock is False


def test_bot_records_non_owner_presence_and_chat_for_later_owner_recap(mock_yorumi):
    prompts = []
    sent = threading.Event()

    def generate(message):
        prompts.append(message)
        return "Alice masuk lalu bahas farm."

    router = AIChatRouter(generator=generate, send_chat=lambda _text: sent.set())
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='44' m='0' s='0' p='2'><n><![CDATA[Alice]]></n>"
        "<vars></vars></u></body></msg>"
    )
    b._handle_server_packet("%xt%chatm%-1%zone~farm lagi rame%Alice%44%273%0%")
    b._handle_server_packet(
        "<msg t='sys'><body action='userGone' r='273'><user id='44' /></body></msg>"
    )

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'><u i='21631' n='ME LE'/></body></msg>"
    )
    assert sent.wait(2)
    sent.clear()
    prompts.clear()

    b._handle_server_packet(
        "%xt%chatm%-1%zone~ada apa ini?%ME LE%21631%273%0%"
    )
    assert sent.wait(2)
    assert "Alice" in prompts[-1]
    assert "farm" in prompts[-1]


def test_owner_user_enter_requests_data_and_locks_immediately(mock_yorumi):
    greeting_sent = threading.Event()
    router = AIChatRouter(
        generator=Mock(return_value="selamat datang"),
        send_chat=lambda _text: greeting_sent.set(),
    )
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'><u i='21631' n='ME LE'/></body></msg>"
    )

    b._client.send.assert_called_once_with(
        sfs.retrieve_user_data_packet(room=273, user_id=21631)
    )
    assert router.enabled is True
    assert router.owner_lock is True
    assert router.active_owner_id == 21631
    assert greeting_sent.wait(2)
    # Confirmation packet remains idempotent and does not create another lock.
    b._handle_server_packet(
        '{"t":"xt","b":{"r":273,"o":{"cmd":"initUserData",'
        '"uid":21631,"data":{}}}}'
    )
    assert router.enabled is True
    assert router.owner_lock is True
    assert router.active_owner_id == 21631


def test_sfs_user_enter_requests_data_then_init_is_idempotent(mock_yorumi):
    sent_chat = Mock()
    router = AIChatRouter(generator=Mock(return_value="selamat datang"), send_chat=sent_chat)
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='uER' r='273'><u i='21623' n='MELE'/></body></msg>"
    )

    b._client.send.assert_called_once_with(
        sfs.retrieve_user_data_packet(room=273, user_id=21623)
    )
    assert router.owner_lock is True
    assert router.enabled is True

    b._handle_server_packet(
        '{"t":"xt","b":{"r":273,"o":{"cmd":"initUserData",'
        '"uid":21623,"data":{}}}}'
    )

    assert router.owner_lock is True
    assert router.active_owner_id == 21623


def test_owner_retrieve_user_data_forces_owner_lock_and_exit_area_resets(mock_yorumi):
    router = AIChatRouter(generator=Mock(return_value="siap"), send_chat=Mock())
    b = bot.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip=mock_yorumi.host, port=mock_yorumi.port,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273

    b._handle_server_packet("%xt%zm%retrieveUserData%273%21623%")
    assert router.enabled is True
    assert router.owner_lock is True
    assert router.owner_present is True
    assert router.active_owner_id == 21623
    assert router.active_owner_name == "MELE"
    # Ulang paket yang sama idempotent: lock tetap aktif tanpa mengganti owner.
    b._handle_server_packet("%xt%zm%retrieveUserData%273%21623%")
    assert router.active_owner_id == 21623

    # Selama owner lock, selain akun pemilik tidak dilayani meski menyebut Mele.
    assert router.handle_message("le jawab dong", "Alice", sender_id=44) is False
    assert router.handle_message("halo", "MELE", sender_id=21623) is True

    b._handle_server_packet("%xt%exitArea%-1%21623%MELE%")
    assert router.enabled is False
    assert router.owner_lock is False
    assert router.owner_present is False
    assert router.active_owner_id is None


def test_owner_can_release_lock_with_mode_normal():
    router = AIChatRouter(generator=Mock(return_value="siap"), send_chat=Mock())
    router.owner_arrived(21631)
    assert router.owner_lock is True

    assert router.handle_message("MODE NORMAL", "ME LE", sender_id=21631) is True
    assert router.owner_lock is False
    assert router.enabled is True
    assert router.handle_message("le jawab", "Alice", sender_id=44) is True

