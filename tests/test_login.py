"""Test HTTP login AQW (stdlib urllib, tanpa menabrak server sungguhan)."""
import io
from unittest.mock import patch

import pytest

from skua_lite import config, login


class _FakeResp(io.BytesIO):
    def __init__(self, body: str):
        super().__init__(body.encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(body: str) -> _FakeResp:
    return _FakeResp(body)


def test_login_returns_token_on_success():
    body = '{"bSuccess":1,"sToken":"XYZ123","unm":"alice","sMsg":""}'
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_ok(body)) as p:
        tok = login.aqw_login("alice", "pw")
    assert tok.username == "alice"
    assert tok.token == "XYZ123"
    assert tok.success is True
    req = p.call_args.args[0]
    assert req.full_url.startswith(config.LOGIN_URL)
    assert "?ran=" in req.full_url


def test_login_raises_on_failure():
    body = '{"bSuccess":0,"sMsg":"Wrong password"}'
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_ok(body)):
        with pytest.raises(login.LoginFailed) as exc:
            login.aqw_login("alice", "wrong")
    assert "Wrong password" in str(exc.value)


def test_login_sends_required_post_fields():
    body = '{"bSuccess":1,"sToken":"T","unm":"a"}'
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        return _ok(body)

    with patch("skua_lite.login.urllib.request.urlopen", side_effect=fake_urlopen):
        login.aqw_login("a", "p")
    req = captured["req"]
    assert req.get_method() == "POST"
    form = req.data.decode()
    assert "user=a" in form
    assert "pass=p" in form
    assert "option=1" in form


def test_login_uses_returned_username_normalized_to_lower():
    body = '{"bSuccess":1,"sToken":"T","unm":"Alice"}'
    with patch("skua_lite.login.urllib.request.urlopen", return_value=_ok(body)):
        tok = login.aqw_login("alice", "p")
    assert tok.username == "alice"
