"""Test framing/protokol SmartFox (verifikasi dari SmartFoxClient.as)."""
from skua_lite import sfs


def test_packet_terminated_with_null_byte():
    raw = sfs.build_packet("<msg t='sys'><body action='verChk' r='0'><ver v='166'/></body></msg>")
    assert raw.endswith(b"\x00")
    assert raw.count(b"\x00") == 1


def test_verchk_matches_client_format():
    pkt = sfs.verchk_packet()
    assert b"<msg t='sys'>" in pkt
    assert b"action='verChk'" in pkt
    assert b"<ver v='157'" in pkt or b"<ver v='157'/>" in pkt


def test_login_packet_uses_zone_master_and_cdata():
    pkt = sfs.login_packet("SPIDER#0001~myuser~3098", "SOMETOKEN")
    assert b"<login z='zone_master'>" in pkt
    assert b"<nick><![CDATA[SPIDER#0001~myuser~3098]]></nick>" in pkt
    assert b"<pword><![CDATA[SOMETOKEN]]></pword>" in pkt
    assert pkt.endswith(b"\x00")


def test_xt_str_packet_format():
    pkt = sfs.xt_str("zm", "cmd", ["tfer", "myuser", "yulgar-14045", "Enter", "Spawn"], room=1)
    body = pkt.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%cmd%1%tfer%myuser%yulgar-14045%Enter%Spawn%"


def test_join_packet_builds_expected_wire_string():
    pkt = sfs.join_packet(username="myuser", map_name="yulgar-14045")
    body = pkt.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%cmd%1%tfer%myuser%yulgar-14045%"


def test_goto_packet_matches_world_as_remote_player_fallback():
    packet = sfs.goto_player_packet("ME LE")
    assert packet.rstrip(b"\x00").decode("latin-1") == (
        "%xt%zm%cmd%1%goto%me le%"
    )


def test_move_to_cell_packet_matches_world_as():
    packet = sfs.move_to_cell_packet(room=42, cell="Boss", pad="Left")
    assert packet.rstrip(b"\x00").decode("latin-1") == (
        "%xt%zm%moveToCell%42%Boss%Left%"
    )


def test_chat_zone_packet():
    pkt = sfs.chat_packet(room=1, message="hello world", channel="zone")
    body = pkt.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%message%1%hello world%zone%"


def test_afk_packet():
    pkt = sfs.afk_packet(room=1)
    body = pkt.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%cmd%1%afk%"


def test_res_player_timed_packet_uses_current_area_room_and_session_uid():
    packet = sfs.res_player_timed_packet(user_id=29467, room=42)
    body = packet.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%resPlayerTimed%42%29467%"


def test_move_packet_uses_room_coordinates_and_speed():
    pkt = sfs.move_packet(room=273, x=850, y=302, speed=10)
    body = pkt.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%mv%273%850%302%10%"


def test_login_response_user_id_parser_uses_uid_field():
    packet = "%xt%loginResponse%-1%true%21030%my user%Welcome!%"
    assert sfs.parse_login_user_id(packet) == 21030
    assert sfs.parse_login_user_id("%xt%server%-1%hello%") is None


def test_retrieve_inventory_packet_contains_session_uid():
    packet = sfs.retrieve_inventory_packet(room=3, user_id=21030)
    body = packet.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%retrieveInventory%3%21030%"


def test_parse_chatm_extracts_channel_message_sender_and_room():
    packet = "%xt%chatm%-1%zone~le lagi ngapain?%Alice%21030%273%0%"
    assert sfs.parse_chat_message(packet) == {
        "channel": "zone",
        "message": "le lagi ngapain?",
        "sender": "Alice",
        "user_id": 21030,
        "room": 273,
    }


def test_parse_chatm_rejects_non_chat_packet():
    assert sfs.parse_chat_message("%xt%loginResponse%-1%true%1%Alice%") is None


def test_parse_exit_area_extracts_user_id_and_username():
    packet = "%xt%exitArea%-1%21030%ME LE%"
    assert sfs.parse_exit_area(packet) == {
        "user_id": 21030,
        "username": "ME LE",
    }
    assert sfs.parse_exit_area("%xt%chatm%-1%zone~hi%Alice%2%273%0%") is None


def test_parse_sfs_user_enter_extracts_id_and_name():
    packet = "<msg t='sys'><body action='uER' r='273'><u i='21623' n='MELE'/></body></msg>"
    assert sfs.parse_user_enter_room(packet) == {
        "room": 273,
        "user_id": 21623,
        "username": "MELE",
    }
    nested = (
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='21631'><n>ME LE</n></u></body></msg>"
    )
    assert sfs.parse_user_enter_room(nested) == {
        "room": 273,
        "user_id": 21631,
        "username": "ME LE",
    }


def test_retrieve_user_data_packet_matches_client_request():
    packet = sfs.retrieve_user_data_packet(room=273, user_id=21623)
    assert packet.rstrip(b"\x00").decode("latin-1") == (
        "%xt%zm%retrieveUserData%273%21623%"
    )


def test_parse_init_user_data_confirms_owner_loaded():
    packet = '{"t":"xt","b":{"r":273,"o":{"cmd":"initUserData",'
    packet += '"uid":21623,"data":{}}}}'
    assert sfs.parse_init_user_data(packet) == {"room":273,"user_id":21623}


def test_parse_retrieve_user_data_request():
    assert sfs.parse_retrieve_user_data("%xt%zm%retrieveUserData%273%21623%") == {
        "room": 273,
        "user_id": 21623,
    }
    assert sfs.parse_retrieve_user_data("%xt%chatm%-1%zone~hi%Alice%2%273%0%") is None


def test_parse_real_user_enter_packet_strips_cdata_name():
    # Exact payload captured live from the AQW server (presence_capture.log).
    packet = (
        "<msg t='sys'><body action='uER' r='273'>"
        "<u i='21943' m='0' s='0' p='2'><n><![CDATA[mele]]></n>"
        "<vars></vars></u></body></msg>"
    )
    assert sfs.parse_user_enter_room(packet) == {
        "room": 273,
        "user_id": 21943,
        "username": "mele",
    }


def test_parse_user_gone_extracts_room_and_user_id():
    # Exact payload captured live from the AQW server (presence_capture.log).
    packet = (
        "<msg t='sys'><body action='userGone' r='273'>"
        "<user id='21943' /></body></msg>"
    )
    assert sfs.parse_user_gone(packet) == {"room": 273, "user_id": 21943}
    assert sfs.parse_user_gone(
        "<msg t='sys'><body action='uER' r='273'><u i='1'/></body></msg>"
    ) is None


def test_framer_splits_multiple_packets():
    fr = sfs.PacketFramer()
    out = fr.feed(b"<a/>\x00<b/>\x00<c")
    assert out == ["<a/>", "<b/>"]
    out2 = fr.feed(b"/>\x00")
    assert out2 == ["<c/>"]


def test_framer_handles_partial_utf8_across_chunks():
    fr = sfs.PacketFramer()
    payload = "caf\u00e9".encode("utf-8")
    assert fr.feed(payload[:2]) == []
    assert fr.feed(payload[2:] + b"\x00") == ["caf\u00e9"]
