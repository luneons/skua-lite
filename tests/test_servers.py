"""Test parser & pemilih server AQW."""
import pytest

from skua_lite import servers

_YORUMI_ONLINE = (
    '[{"sName":"Twilly","sIP":"sock7.aq.com","iCount":592,"iMax":1000,'
    '"bOnline":1,"iChat":0,"bUpg":0,"iPort":5593},'
    '{"sName":"Yorumi","sIP":"sock8.aq.com","iCount":170,"iMax":1500,'
    '"bOnline":1,"iChat":2,"bUpg":0,"iPort":5588}]'
)


def test_parse_server_list_finds_yorumi():
    out = servers.parse_server_list(_YORUMI_ONLINE)
    assert "Yorumi" in out
    y = out["Yorumi"]
    assert y.ip == "sock8.aq.com"
    assert y.port == 5588
    assert y.online is True
    assert y.full is False


def test_pick_returns_server_when_online_with_room():
    s = servers.pick(servers.parse_server_list(_YORUMI_ONLINE), "Yorumi")
    assert s.name == "Yorumi"
    assert s.ip == "sock8.aq.com"
    assert s.port == 5588


def test_pick_raises_when_offline():
    payload = ('[{"sName":"Yorumi","sIP":"sock8.aq.com","iCount":170,'
               '"iMax":1500,"bOnline":0,"iPort":5588}]')
    with pytest.raises(servers.ServerUnavailable):
        servers.pick(servers.parse_server_list(payload), "Yorumi")


def test_pick_raises_when_full():
    payload = ('[{"sName":"Yorumi","sIP":"sock8.aq.com","iCount":1500,'
               '"iMax":1500,"bOnline":1,"iPort":5588}]')
    with pytest.raises(servers.ServerUnavailable):
        servers.pick(servers.parse_server_list(payload), "Yorumi")


def test_pick_unknown_server_raises():
    with pytest.raises(servers.ServerUnavailable):
        servers.pick({}, "NoSuchServer")
