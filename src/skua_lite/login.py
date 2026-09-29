"""HTTP login ke AQW (stdlib-only: zero external deps).

Server saat ini membungkus field login di bawah kunci 'login'. Field
objLogin yang dipake client AQW (Game.as onLoginComplete):

    if(_obj.login)
        objLogin = _obj.login;
    else
        objLogin = _obj;
    if(objLogin.bSuccess == 1)
        loginInfo.strToken = objLogin.sToken;
        loginInfo.strUsername = objLogin.unm.toLowerCase();

Jadi parser kita meng-unwrap dulu bila wrapper ada, agar kompatibel dengan
shape baru sekaligus mempertahankan fallback ke shape lama.
"""
from __future__ import annotations

import json
import random
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class LoginToken:
    username: str
    token: str
    success: bool
    message: str = ""
    level: int = 1

    @classmethod
    def from_objlogin(cls, obj_login: dict, fallback_username: str = "") -> "LoginToken":
        level = 1
        raw_level = obj_login.get("iLevel", 1)
        try:
            level = int(raw_level) if not isinstance(raw_level, bool) else 1
        except (TypeError, ValueError):
            level = 1
        return cls(
            username=str(obj_login.get("unm", "") or fallback_username),
            token=str(obj_login.get("sToken", "")),
            success=bool(obj_login.get("bSuccess", 0) == 1),
            message=str(obj_login.get("sMsg", "")),
            level=level,
        )


class LoginFailed(Exception):
    """Login ditolak server (password salah, akun terkunci, dll)."""


def _unwrap_objlogin(data) -> dict:
    """Server terkini membungkus field login di dalam 'login'; dukung keduanya."""
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("login"), dict):
        return data["login"]
    return data


def aqw_login(username: str, password: str, *, timeout: float = 20.0) -> LoginToken:
    """POST ke AQW login API dan kembalikan token sesi."""
    rand = str(random.random())
    url = f"{config.LOGIN_URL}?ran={rand}"
    form = urllib.parse.urlencode(
        {"user": username, "pass": password, "option": "1"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=form,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AQW/Skua-Lite",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise LoginFailed(f"jaringan login gagal: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LoginFailed(f"login: balasan non-JSON ({raw[:100]})") from e

    obj_login = _unwrap_objlogin(data)
    tok = LoginToken.from_objlogin(obj_login, fallback_username=username)
    if not tok.success or not tok.token:
        # PENTING: jangan pernah mencetak raw `data` — raw response bisa berisi
        # sToken (token sesi), email, dan informasi akun sensitif lainnya.
        msg = tok.message or (obj_login.get("sMsg") if isinstance(obj_login, dict) else "") or "autentikasi ditolak"
        raise LoginFailed(f"login gagal: {msg}")
    return LoginToken(
        username=tok.username.lower(),
        token=tok.token,
        success=True,
        message=tok.message,
        level=tok.level,
    )
