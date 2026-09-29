"""Regression tests for the owner-only follow mode (\"Ikuti aku\").

Evidence-grounded packet shapes:
- owner movement: JSON ``uotls`` with ``o`` carrying ``strFrame``/``strPad``
  and ``tx``/``ty``/``sp`` (AQW decompile ``Game.as:1411-1420`` + ``5377+``;
  STR form ``%xt%uotls%-1%<name>%k:v,%`` like area_state tests).
- owner leaves: ``exitArea`` / ``userGone`` (already parsed by ``sfs``).
- bot mirror: ``%xt%zm%mv%<room>%<x>%<y>%<speed>%`` (``World.as:3491``),
  ``%xt%zm%moveToCell%<room>%<cell>%<pad>%`` (``World.as:2884``),
  ``%xt%zm%cmd%1%goto%<name>%`` when the owner is no longer in the area.
"""
from unittest.mock import Mock

from skua_lite import bot as bot_mod
from skua_lite.ai_router import AIChatRouter
from skua_lite.servers import Server


def _follow_bot(router=None):
    router = router or AIChatRouter(
        generator=Mock(return_value="ignored"),
        send_chat=Mock(),
    )
    b = bot_mod.AQWBot(
        username="myuser",
        token="T",
        server=Server(
            name="Yorumi", ip="127.0.0.1", port=5588,
            online=True, full=False, upgrade_only=False,
        ),
        ai_router=router,
    )
    b.room_id = 273
    b._client = Mock()
    b.state = bot_mod.BotState.IN_MAP
    return b, router


def _owner_chat(b, text, uid=21623, name="mele"):
    b._handle_server_packet(
        f"%xt%chatm%-1%zone~{text}%{name}%{uid}%273%0%"
    )


def _sent(b):
    out = []
    for call in b._client.send.call_args_list:
        raw = call.args[0] if call.args else call[0][0]
        out.append(raw.rstrip(b"\x00").decode("latin-1"))
    return out


def _owner_uotls(b, **fields):
    encoded = ",".join(f"{key}:{value}" for key, value in fields.items())
    b._handle_server_packet(f"%xt%uotls%-1%mele%{encoded}%")


# --- command gating -------------------------------------------------------

def test_follow_starts_only_for_active_owner_exact_phrase():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")

    _owner_chat(b, "Ikuti aku")
    assert b.follow.is_following is True

    b.follow.stop()
    _owner_chat(b, "ikuti AKU ya dong")
    assert b.follow.is_following is False


def test_non_owner_cannot_start_follow():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")

    _owner_chat(b, "Ikuti aku", uid=777, name="alice")
    assert b.follow.is_following is False


def test_owner_stop_phrase_ends_follow():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")

    _owner_chat(b, "Ikuti aku")
    assert b.follow.is_following is True
    _owner_chat(b, "Berhenti ikuti aku")
    assert b.follow.is_following is False


# --- in-area mirroring -----------------------------------------------------

def test_follow_mirrors_owner_cell_change():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")
    b._client.send.reset_mock()

    _owner_uotls(b, strFrame="Boss", strPad="Left")

    assert "%xt%zm%moveToCell%273%Boss%Left%" in _sent(b)


def test_follow_mirrors_owner_coordinates():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")
    b._client.send.reset_mock()

    _owner_uotls(b, tx=850, ty=302, sp=10)

    assert "%xt%zm%mv%273%850%302%10%" in _sent(b)


def test_follow_ignores_other_players_movement():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")
    b._client.send.reset_mock()

    b._handle_server_packet("%xt%uotls%-1%alice%strFrame:Boss,strPad:Left%")
    b._handle_server_packet("%xt%uotls%-1%alice%tx:1,ty:2,sp:10%")

    assert _sent(b) == []


def test_follow_stays_quiet_when_owner_leaves_and_sends_goto():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")
    b._client.send.reset_mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='userGone' r='273'>"
        "<user id='21623' /></body></msg>"
    )

    sent = _sent(b)
    assert "%xt%zm%cmd%1%goto%mele%" in sent
    assert not any("%moveToCell%" in packet for packet in sent)
    assert not any(packet.startswith("%xt%zm%mv%") for packet in sent)


def test_follow_resumes_after_owner_returns():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")

    b._handle_server_packet(
        "<msg t='sys'><body action='userGone' r='273'>"
        "<user id='21623' /></body></msg>"
    )
    assert b.follow.is_following is True

    b._client.send.reset_mock()
    _owner_uotls(b, strFrame="Boss", strPad="Left")
    assert "%xt%zm%moveToCell%273%Boss%Left%" in _sent(b)


def test_owner_leaving_room_stops_owner_lock_but_keeps_follow():
    b, router = _follow_bot()
    router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")

    b._handle_server_packet("%xt%exitArea%-1%21623%mele%")

    assert b.follow.is_following is True
    assert "%xt%zm%cmd%1%goto%mele%" in _sent(b)


def test_follow_sends_goto_only_once_when_both_departure_signals_arrive():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")
    b._client.send.reset_mock()

    b._handle_server_packet(
        "<msg t='sys'><body action='userGone' r='273'>"
        "<user id='21623' /></body></msg>"
    )
    b._handle_server_packet("%xt%exitArea%-1%21623%mele%")

    gotos = [p for p in _sent(b) if "goto" in p]
    assert len(gotos) == 1


def test_follow_goto_guard_resets_when_owner_returns():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti aku")

    b._handle_server_packet("%xt%exitArea%-1%21623%mele%")
    _owner_uotls(b, strFrame="Boss", strPad="Left")
    b._client.send.reset_mock()

    b._handle_server_packet("%xt%exitArea%-1%21623%mele%")
    gotos = [p for p in _sent(b) if "goto" in p]
    assert len(gotos) == 1


def test_no_follow_traffic_without_active_mode():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    # Mode never enabled: owner movement must not move the bot at all.
    _owner_uotls(b, strFrame="Boss", strPad="Left")
    _owner_uotls(b, tx=850, ty=302, sp=10)

    assert _sent(b) == []
