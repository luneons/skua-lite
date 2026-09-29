"""Test: parser harus support respons API yang membungkus data di bawah 'login'.

Bentuk respons nyata (dari server produksi):

    {"login": {"bSuccess":1, "sToken":"...", "unm":"...", "sMsg":"success", ...},
     "servers": [...], "polldata": {}}

Client AQW sendiri meng-unwrap: `objLogin = data.login` bila ada.
"""
import io
from unittest.mock import patch

import pytest

from skua_lite import login


class _Resp(io.BytesIO):
    def __init__(self, b): super().__init__(b.encode("utf-8"))
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _wrap(body: str) -> _Resp:
    return _Resp(body)


_NESTED_OK = """{
  "login": {
    "bSuccess": 1, "userid": 12345678, "iAccess": 0, "iUpg": 0,
    "iAge": 63, "iLevel": 100, "iUpgDays": -980, "bCCOnly": 0,
    "intHours": 0, "iEmailStatus": 1, "sMsg": "success",
    "sToken": "FAKE-SESSION-TOKEN", "unm": "Test User",
    "strCountryCode": "ID", "strEmail": "user@example.test"
  },
  "servers": [{"sName":"Yorumi","sIP":"sock8.aq.com","iCount":166,
                "iMax":1500,"bOnline":1,"iPort":5588}],
  "polldata": {}
}"""

_NESTED_FAIL = '{"login": {"bSuccess": 0, "sMsg": "Wrong password"}}'


def test_extracts_token_from_nested_login_object():
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_wrap(_NESTED_OK)):
        tok = login.aqw_login("Test User", "sekret")
    assert tok.success is True
    assert tok.token == "FAKE-SESSION-TOKEN"
    assert tok.message == "success"
    # Game.as memakai objLogin.unm.toLowerCase()
    assert tok.username == "test user"


def test_failure_message_taken_from_nested_login():
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_wrap(_NESTED_FAIL)):
        with pytest.raises(login.LoginFailed) as exc:
            login.aqw_login("alice", "wrong")
    assert "Wrong password" in str(exc.value)


def test_legacy_flat_shape_still_supported():
    body = '{"bSuccess":1,"sToken":"LEGACY","unm":"alice","sMsg":""}'
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_wrap(body)):
        tok = login.aqw_login("alice", "pw")
    assert tok.token == "LEGACY"
    assert tok.username == "alice"


def test_legacy_failure_shape_works():
    body = '{"bSuccess":0,"sMsg":"legacy err"}'
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_wrap(body)):
        with pytest.raises(login.LoginFailed) as exc:
            login.aqw_login("alice", "pw")
    assert "legacy err" in str(exc.value)
