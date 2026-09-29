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


def _uER(b, username, uid):
    b._handle_server_packet(
        f"<msg t='sys'><body action='uER' r='273'>"
        f"<u i='{uid}' n='{username}' /></body></msg>"
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
    _owner_chat(b, "Berhenti")
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


def test_owner_follow_other_player_command_starts_and_mirrors_target():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _uER(b, "alice", 777)

    _owner_chat(b, "Ikuti alice")
    assert b.follow.is_following is True
    assert b.follow.owner_name == "alice"
    b._client.send.reset_mock()

    b._handle_server_packet("%xt%uotls%-1%alice%strFrame:Boss,strPad:Left%")
    b._handle_server_packet("%xt%uotls%-1%alice%tx:1,ty:2,sp:10%")
    sent = _sent(b)
    assert "%xt%zm%moveToCell%273%Boss%Left%" in sent
    assert "%xt%zm%mv%273%1%2%10%" in sent

    # The owner's own movement is no longer mirrored while another target is
    # being followed.
    b._client.send.reset_mock()
    _owner_uotls(b, strFrame="Boss", strPad="Left")
    assert "Boss" not in " ".join(_sent(b))


def test_follow_other_player_ignores_strangers_and_owner_commands_still_gate():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    _uER(b, "alice", 777)

    # Only the active owner can aim the follower at someone else.
    _owner_chat(b, "Ikuti alice", uid=777, name="alice")
    assert b.follow.is_following is False

    _owner_chat(b, "Ikuti alice")
    assert b.follow.is_following is True

    b._client.send.reset_mock()
    b._handle_server_packet("%xt%uotls%-1%bob%strFrame:Boss,strPad:Left%")
    b._handle_server_packet("%xt%uotls%-1%bob%tx:9,ty:9,sp:10%")
    assert _sent(b) == []


def _wait_for(predicate, timeout=3.0):
    """Poll until the background return-home thread has finished its work."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_stop_then_return_home_moves_to_home_and_sets_afk():
    b, _ = _follow_bot()
    b.target_map = "yulgar-14045"
    b.current_map = "yulgar-14045"  # already home: no map join needed
    b.ai_router.owner_arrived(21623, "mele")

    _owner_chat(b, "Ikuti alice")
    assert b.follow.is_following is True
    b._client.send.reset_mock()

    _owner_chat(b, "Berhenti")
    assert b.follow.is_following is False
    assert _wait_for(lambda: b.is_afk is True) is True

    sent = _sent(b)
    assert "%xt%zm%moveToCell%273%Enter%Spawn%" in sent
    assert "%xt%zm%mv%273%850%302%10%" in sent
    assert sent[-1] == "%xt%zm%afk%1%true%"


def test_stop_returns_home_through_join_when_followed_away(monkeypatch):
    b, _ = _follow_bot()
    b.target_map = "yulgar-14045"
    b.current_map = "lair-97940"
    b.ai_router.owner_arrived(21623, "mele")
    _owner_chat(b, "Ikuti alice")
    b._client.send.reset_mock()

    joined: list[str] = []

    def fake_join(map_name):
        joined.append(map_name)
        b.current_map = map_name
        b.room_id = 273

    monkeypatch.setattr(b, "join_map", fake_join)
    _owner_chat(b, "Berhenti")

    assert _wait_for(lambda: b.is_afk is True) is True
    assert joined == ["yulgar-14045"]
    assert b.follow.is_following is False
    assert "%xt%zm%afk%1%true%" in _sent(b)


def test_stop_while_not_following_does_not_yank_bot_home():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    b._client.send.reset_mock()

    _owner_chat(b, "Berhenti")

    # Nothing to stop: the word must not move the bot or make it AFK.
    assert _sent(b) == []
    assert b.is_afk is False


def test_stop_word_is_still_gated_to_active_owner():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")

    _owner_chat(b, "Ikuti alice")
    assert b.follow.is_following is True

    _owner_chat(b, "Berhenti", uid=777, name="alice")
    assert b.follow.is_following is True


def test_no_follow_traffic_without_active_mode():
    b, _ = _follow_bot()
    b.ai_router.owner_arrived(21623, "mele")
    # Mode never enabled: owner movement must not move the bot at all.
    _owner_uotls(b, strFrame="Boss", strPad="Left")
    _owner_uotls(b, tx=850, ty=302, sp=10)

    assert _sent(b) == []
