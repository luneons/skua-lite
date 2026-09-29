"""Unit tests for follow command parsing and the OwnerFollower controller."""
from skua_lite.follow import (
    OwnerFollower,
    normalize_command,
    parse_follow_command,
)


def test_parse_follow_command_matches_expected_phrases():
    assert parse_follow_command("Ikuti aku") == "start"
    assert parse_follow_command("  IKUTI   AKU  ") == "start"
    assert parse_follow_command("Berhenti ikuti aku") == "stop"
    assert parse_follow_command("Stop ikuti aku") == "stop"


def test_parse_follow_command_rejects_lookalikes():
    assert parse_follow_command("ikuti aku dong") is None
    assert parse_follow_command("tolong ikuti aku") is None
    assert parse_follow_command("jangan ikuti aku ya?") is None
    assert normalize_command("  Ikuti\tAku ") == "ikuti aku"


def test_follower_ignores_non_owner_and_dedupes_updates():
    follower = OwnerFollower()
    follower.start("mele", 21623)

    assert follower.matches("alice", 777) is False
    # Name match is accepted when the UID is unknown (session IDs rotate).
    assert follower.matches("MELE") is True

    first = follower.packets_for_update(
        273, "mele", {"strFrame": "Boss", "strPad": "Left", "tx": 850, "ty": 302, "sp": 10}
    )
    assert len(first) == 2
    repeat = follower.packets_for_update(
        273, "mele", {"strFrame": "Boss", "strPad": "Left", "tx": 850, "ty": 302, "sp": 10}
    )
    assert repeat == []


def test_follower_departure_sends_single_goto_and_stops_cleanly():
    follower = OwnerFollower()
    assert follower.packets_for_departure() == []
    follower.start("mele", 21623)

    goto = follower.packets_for_departure()
    assert len(goto) == 1
    assert goto[0].rstrip(b"\x00").decode("latin-1") == "%xt%zm%cmd%1%goto%mele%"

    follower.stop()
    assert follower.is_following is False
    assert follower.matches("mele", 21623) is False
    assert follower.packets_for_departure() == []
