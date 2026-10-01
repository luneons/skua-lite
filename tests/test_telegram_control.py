"""Panel kontrol Telegram: parser, otorisasi, dan pengiriman balasan."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from skua_lite import telegram_control as tg


class FakeTransport:
    """Transport rekaman: tidak pernah menyentuh jaringan."""

    def __init__(self, updates=None):
        self.sent: list[tuple] = []
        self.answered: list[tuple] = []
        self.edits: list[tuple] = []
        self.button_answers: list[tuple] = []
        self.offsets: list[int | None] = []
        self.get_me_calls = 0
        self._updates = list(updates or [])
        self.fail_with: Exception | None = None

    def get_me(self):
        self.get_me_calls += 1
        return {"id": 7, "username": "skua_bot", "first_name": "Skua"}

    def get_updates(self, offset=None, timeout=25):
        self.offsets.append(offset)
        if self.fail_with is not None:
            raise self.fail_with
        if self._updates:
            return self._updates.pop(0)
        raise tg.TelegramNetworkError("tidak ada update")

    def send_photo(self, chat_id, image_bytes, *, caption="", buttons=None):
        self.sent.append((chat_id, f"[PHOTO: {len(image_bytes)}b] {caption}", buttons))
        return {"message_id": len(self.sent)}

    def send_message(self, chat_id, text, *, buttons=None):
        self.sent.append((chat_id, text, buttons))
        return {"message_id": len(self.sent)}

    def answer_callback_query(self, callback_id, text=""):
        self.answered.append((callback_id, text))
        return True

    def edit_message_text(self, chat_id, message_id, text, *, buttons=None):
        self.edits.append((chat_id, message_id, text, buttons))
        return True


def _record_command(calls):
    def run_command(orch, action, arg):
        calls.append((action, arg))
        print(f"[FAKE] {action} {arg}".strip())
        return "farm"

    return run_command


def _control(transport, calls, *, owner_id=555, orch=None):
    return tg.TelegramControl(
        orch if orch is not None else SimpleNamespace(),
        transport,
        owner_id=owner_id,
        run_command=_record_command(calls),
    )


def _message(text, *, user_id=555, chat_id=99):
    return {
        "message_id": 1,
        "from": {"id": user_id, "first_name": "Boss"},
        "chat": {"id": chat_id, "type": "private"},
        "text": text,
    }


def _callback(data, *, user_id=555, chat_id=99, message_id=5):
    return {
        "id": "cb1",
        "from": {"id": user_id, "first_name": "Boss"},
        "message": {"message_id": message_id, "chat": {"id": chat_id}},
        "data": data,
    }


# ---------------------------------------------------------------- config


def test_config_reads_token_and_owner_from_dotenv_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SKUA_TELEGRAM_TOKEN=123:file-token\n"
        "SKUA_TELEGRAM_OWNER_ID=987654321\n",
        encoding="utf-8",
    )

    config = tg.TelegramConfig.from_env({}, env_file=env_file)

    assert config.token == "123:file-token"
    assert config.owner_id == 987654321


def test_process_environment_overrides_dotenv_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SKUA_TELEGRAM_TOKEN=123:file-token\n"
        "SKUA_TELEGRAM_OWNER_ID=111\n",
        encoding="utf-8",
    )

    config = tg.TelegramConfig.from_env(
        {"SKUA_TELEGRAM_TOKEN": "456:process-token", "SKUA_TELEGRAM_OWNER_ID": "222"},
        env_file=env_file,
    )

    assert config.token == "456:process-token"
    assert config.owner_id == 222


def test_config_reads_token_and_owner_from_env():
    config = tg.TelegramConfig.from_env({
        "SKUA_TELEGRAM_TOKEN": "123:abc",
        "SKUA_TELEGRAM_OWNER_ID": "555",
    })

    assert config.token == "123:abc"
    assert config.owner_id == 555
    assert config.enabled is True


def test_config_without_token_is_disabled(tmp_path):
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    config = tg.TelegramConfig.from_env({}, env_file=empty_env)

    assert config.enabled is False
    assert config.owner_id is None


def test_config_rejects_non_numeric_owner_id(tmp_path):
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    config = tg.TelegramConfig.from_env({
        "SKUA_TELEGRAM_TOKEN": "123:abc",
        "SKUA_TELEGRAM_OWNER_ID": "bukan-angka",
    }, env_file=empty_env)

    assert config.token == "123:abc"
    assert config.owner_id is None

# ---------------------------------------------------------------- parser


def test_slash_command_maps_to_the_same_farm_command_set():
    assert tg.parse_telegram_command("/join yulgar -private") == ("join", "yulgar -private")
    assert tg.parse_telegram_command("/level 80") == ("level", "80")
    assert tg.parse_telegram_command("/attack Bone Berserker") == ("attack", "Bone Berserker")
    assert tg.parse_telegram_command("/dashboard") == ("dashboard", "")


def test_slash_command_syntax_forms_normalize_identically():
    assert tg.parse_telegram_command("/level@skua_bot 80") == ("level", "80")
    assert tg.parse_telegram_command("level 80") == ("level", "80")
    assert tg.parse_telegram_command(".level 80") == ("level", "80")


def test_unknown_slash_command_is_refused_not_guessed():
    assert tg.parse_telegram_command("/rm -rf /") == ("", "")
    assert tg.parse_telegram_command("/keluar") == ("", "")


def test_help_and_panel_are_handled_specially():
    assert tg.parse_telegram_command("/start") == ("__help__", "")
    assert tg.parse_telegram_command("/help") == ("__help__", "")
    assert tg.parse_telegram_command("/panel") == ("__panel__", "")
    assert tg.parse_telegram_command("/stop") == ("__stop__", "")


# ---------------------------------------------------------------- authorization


def test_non_owner_message_is_refused_without_running_any_command():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_message(_message("/level 80", user_id=999))

    assert calls == []
    assert "bukan owner" in transport.sent[0][1].lower()


def test_unknown_owner_id_reports_sender_id_and_runs_nothing():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls, owner_id=None)

    control.handle_message(_message("/status", user_id=12345))

    assert calls == []
    assert "12345" in transport.sent[0][1]


def test_owner_message_runs_command_and_replies_with_runtime_output():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_message(_message("/join oaklore -private"))

    assert calls == [("join", "oaklore -private")]
    assert "(join, 'oaklore -private')" not in transport.sent[0][1]
    assert "[FAKE] join oaklore -private" in transport.sent[0][1]


def test_refused_command_reports_usage_instead_of_silence():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_message(_message("/rm -rf /"))

    assert calls == []
    assert transport.sent, "harus ada balasan"
    assert "/help" in transport.sent[0][1]


# ---------------------------------------------------------------- panel + callbacks


def test_dashboard_reply_carries_inline_buttons():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_message(_message("/panel"))

    chat_id, text, buttons = transport.sent[0]
    assert chat_id == 99
    labels = [button["text"] for row in buttons for button in row]
    assert "Dashboard" in labels
    assert any("-private" in button["callback_data"] for row in buttons for button in row)


def test_callback_button_runs_its_command_and_answers_the_press():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_callback(_callback("cmd|level|100 -private"))

    assert calls == [("level", "100 -private")]
    assert transport.answered and transport.answered[0][0] == "cb1"


def test_callback_from_non_owner_is_refused_and_command_not_run():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_callback(_callback("cmd|level|100", user_id=999))

    assert calls == []
    assert transport.answered, "callback harus tetap dijawab agar tombol tidak ngegantung"


def test_stop_command_stops_leveling_attack_and_goal():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls)

    control.handle_message(_message("/stop"))

    assert ("level", "stop") in calls
    assert ("attack", "off") in calls
    assert ("auto", "stop") in calls


def test_gantiakun_shows_account_picker_when_accounts_exist():
    transport = FakeTransport()
    calls: list[tuple] = []
    accounts = SimpleNamespace(
        list_usernames=lambda: ["Hero123", "AltAccount"],
        active_username=lambda: "Hero123",
    )
    orch = SimpleNamespace(
        server_name="Yorumi",
        bot=None,
        accounts=accounts,
        store=None,
    )
    control = _control(transport, calls, orch=orch)

    control.handle_message(_message("/gantiakun"))

    text = transport.sent[0][1]
    buttons = transport.sent[0][2]
    assert "PILIH AKUN" in text
    assert "Hero123" in text
    flat = [b["text"] for row in buttons for b in row]
    assert any("Hero123" in t for t in flat)
    assert any("AltAccount" in t for t in flat)


def test_gantiakun_shows_empty_hint_when_no_accounts():
    transport = FakeTransport()
    calls: list[tuple] = []
    accounts = SimpleNamespace(
        list_usernames=lambda: [],
        active_username=lambda: None,
    )
    orch = SimpleNamespace(server_name="Yorumi", bot=None, accounts=accounts, store=None)
    control = _control(transport, calls, orch=orch)

    control.handle_message(_message("/gantiakun"))

    text = transport.sent[0][1]
    assert ".tambahakun" in text


def test_callback_acc_calls_switch_account_by_name():
    transport = FakeTransport()
    calls: list[tuple] = []
    switched: list[str] = []
    orch = SimpleNamespace(
        switch_account_by_name=lambda u: switched.append(u) or f"OK pindah ke {u}",
    )
    control = _control(transport, calls, orch=orch)

    control.handle_callback(_callback("special|acc|AltAccount"))

    assert switched == ["AltAccount"]
    assert "AltAccount" in transport.edits[0][2]


def test_tambahakun_cli_adds_to_multi_account_store():
    from skua_lite.cli import parse_farm_command, dispatch_farm

    saved: dict[str, str] = {}

    class FakeAccounts:
        def add_account(self, u, p):
            saved[u] = p

    orch = SimpleNamespace(farming=object(), bot=None, accounts=FakeAccounts())

    action, arg = parse_farm_command(".tambahakun newuser newpass")
    assert action == "tambahakun"

    dispatch_farm(orch, action, arg)
    assert saved == {"newuser": "newpass"}

def test_settings_and_change_server_commands():
    calls: list[tuple] = []
    transport = FakeTransport()
    orch = SimpleNamespace(
        server_name="Yorumi",
        bot=SimpleNamespace(username="Hero123", current_map="oaklore-1", state="IN_MAP"),
        store=SimpleNamespace(load=lambda: ("Hero123", "pw")),
        accounts=SimpleNamespace(list_usernames=lambda: [], active_username=lambda: None),
        switch_server=lambda s: f"OK: switch ke {s}",
    )
    control = _control(transport, calls, orch=orch)

    # 1. /pengaturan
    control.handle_message(_message("/pengaturan"))
    assert len(transport.sent) == 1
    assert "Hero123" in transport.sent[0][1]
    assert "Yorumi" in transport.sent[0][1]

    # 2. /gantiserver dengan nama server
    control.handle_message(_message("/gantiserver Artix"))
    assert "switch ke Artix" in transport.sent[1][1]

    # 3. /gantiakun (tidak ada akun tersimpan -> tampilkan panduan)
    control.handle_message(_message("/gantiakun"))
    assert ".tambahakun" in transport.sent[2][1]

    # 4. Callback settings
    control.handle_callback(_callback("special|settings|"))
    assert "PENGATURAN" in transport.edits[0][2]

    # 5. Callback srv
    control.handle_callback(_callback("special|srv|Twilly"))
    assert "switch ke Twilly" in transport.edits[1][2]


# ---------------------------------------------------------------- polling


def test_poll_once_advances_offset_past_handled_updates():
    calls: list[tuple] = []
    transport = FakeTransport([[{"update_id": 10, "message": _message("/status")}]])
    control = _control(transport, calls)

    offset = control.poll_once(None)

    assert offset == 11
    assert calls == [("status", "")]


def test_poll_once_ignores_unrelated_update_shapes():
    calls: list[tuple] = []
    transport = FakeTransport([[{"update_id": 3, "edited_message": {"text": "/level 80"}}]])
    control = _control(transport, calls)

    assert control.poll_once(None) == 4
    assert calls == []


def test_serve_treats_three_consecutive_conflicts_as_fatal():
    transport = FakeTransport()
    transport.fail_with = tg.TelegramConflict("terminated by other getUpdates")
    logs: list[str] = []
    control = _control(transport, [])

    control.serve(stop_event=_NeverSet(), on_log=logs.append, conflict_limit=3)

    assert len(transport.offsets) == 3
    assert any("409" in line or "konflik" in line.lower() for line in logs)


def test_serve_recovers_from_network_errors():
    transport = FakeTransport([[{"update_id": 1, "message": _message("/status")}]])
    calls: list[tuple] = []
    control = _control(transport, calls)
    logs: list[str] = []

    control.serve(stop_event=_StopAfter(2), on_log=logs.append)

    assert calls == [("status", "")]
    assert any("gagal" in line.lower() or "error" in line.lower() for line in logs)


# ---------------------------------------------------------------- transport hygiene


def test_reply_is_truncated_to_telegram_message_limit():
    calls: list[tuple] = []
    transport = FakeTransport()
    control = _control(transport, calls, orch=SimpleNamespace())

    def run_command(orch, action, arg):
        print("x" * 9000)
        return "farm"

    control.run_command = run_command
    control.handle_message(_message("/status"))

    body = transport.sent[0][1]
    assert len(body) <= tg.MAX_MESSAGE_CHARS
    assert body.endswith(tg.TRUNCATION_MARKER)


class _NeverSet:
    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        return False


class _StopAfter:
    """Stop event yang menutup setelah N panggilan wait()."""

    def __init__(self, limit: int):
        self.limit = limit
        self.calls = 0

    def is_set(self) -> bool:
        return self.calls >= self.limit

    def wait(self, timeout: float) -> bool:
        self.calls += 1
        return self.is_set()

def test_screenshot_command_parses_as_special():
    assert tg.parse_telegram_command("/ss") == ("__screenshot__", "")
    assert tg.parse_telegram_command("/screenshot") == ("__screenshot__", "")
    assert tg.parse_telegram_command("/kondisi") == ("__screenshot__", "")


def test_screenshot_without_known_username_warns_cleanly():
    transport = FakeTransport()
    calls = []
    control = _control(transport, calls)

    control.handle_message(_message("/ss"))

    assert len(transport.sent) == 1
    chat_id, text, _ = transport.sent[0]
    assert chat_id == 99
    assert "username" in text.lower()


def test_screenshot_with_bot_username_falls_back_cleanly_on_offline_render():
    transport = FakeTransport()
    calls = []
    orch = SimpleNamespace(
        bot=SimpleNamespace(
            username="TestHero",
            current_map="battleon",
            state="IDLE",
            level=100,
            combat=SimpleNamespace(class_name="Void Highlord"),
        )
    )
    control = _control(transport, calls, orch=orch)

    # Calling /ss when network is offline triggers fallback text summary
    control.handle_message(_message("/ss"))

    assert len(transport.sent) == 1
    _, text, _ = transport.sent[0]
    assert "TestHero" in text
    assert "Void Highlord" in text
    assert "battleon" in text

# ---------------------------------------------------------------- multi-account join broadcast


def test_telegram_join_broadcasts_to_all_multi_accounts():
    from skua_lite.multi_session import MultiOrchestrator

    transport = FakeTransport()
    calls1 = []
    calls2 = []

    def make_slot(calls):
        b = Mock()
        b.join_map = Mock(side_effect=lambda m: calls.append(f"joined {m}"))
        f = Mock()
        f.join = Mock(side_effect=lambda m, private=False: calls.append(f"farm_join {m} private={private}"))
        return SimpleNamespace(bot=b, farming=f, server_name="Yorumi")

    mo = MultiOrchestrator()
    mo.add_slot("Acc1", make_slot(calls1))
    mo.add_slot("Acc2", make_slot(calls2))

    control = _control(transport, [], orch=mo)
    control.handle_message(_message("/join sevencircleswar -private"))

    assert len(transport.sent) == 1
    reply = transport.sent[0][1]
    assert "=== HASIL 2 AKUN ===" in reply
    assert "[Acc1]" in reply
    assert "[Acc2]" in reply
    assert calls1 == ["farm_join sevencircleswar private=True"]
    assert calls2 == ["farm_join sevencircleswar private=True"]

# ---------------------------------------------------------------- /tambahakun safe flow on Telegram


def test_tambahakun_on_telegram_blocks_passwords_and_instructs_safe_methods():
    """Telegram tidak boleh menerima atau menyimpan password; harus memandu cara aman."""
    transport = FakeTransport()
    control = _control(transport, [])

    control.handle_message(_message("/tambahakun"))

    assert len(transport.sent) == 1
    reply = transport.sent[0][1]
    assert "keamanan" in reply.lower() or "aman" in reply.lower()
    assert ".tambahakun" in reply
    assert "akun.txt" in reply
    assert "/gantiakun" in reply


# ---------------------------------------------------------------- startup buttons context


def test_startup_mode_shows_startup_buttons_not_farming_buttons():
    """Saat startup, tombol tidak boleh Dashboard/Combat/Leveling melainkan tombol startup."""
    transport = FakeTransport()
    calls: list[tuple] = []
    startup_orch = SimpleNamespace(bot=None, farming=None, startup=True)
    control = _control(transport, calls, orch=startup_orch)

    control.handle_message(_message("/panel"))

    assert len(transport.sent) == 1
    _, text, buttons = transport.sent[0]
    assert "STARTUP" in text
    labels = [b["text"] for row in buttons for b in row]
    assert "Dashboard" not in labels
    assert "Combat" not in labels
    assert "Level 100 Public" not in labels
    assert any("Cek Status" in l for l in labels)
    assert any("Panduan" in l for l in labels)


def test_startup_callback_guide_shows_mode_and_login_steps():
    transport = FakeTransport()
    calls: list[tuple] = []
    startup_orch = SimpleNamespace(bot=None, farming=None, startup=True)
    control = _control(transport, calls, orch=startup_orch)

    control.handle_callback(_callback("special|startup_guide|"))

    assert len(transport.edits) == 1
    _, _, text, buttons = transport.edits[0]
    assert "MODE AI ASISTEN" in text
    assert "MODE FARMING" in text
    labels = [b["text"] for row in buttons for b in row]
    assert any("Cek Status" in l for l in labels)


def test_attaching_connected_orch_switches_buttons_back_to_farming():
    transport = FakeTransport()
    calls: list[tuple] = []
    startup_orch = SimpleNamespace(bot=None, farming=None, startup=True)
    control = _control(transport, calls, orch=startup_orch)

    # Saat startup -> tombol startup
    control.handle_message(_message("/panel"))
    labels_startup = [b["text"] for row in transport.sent[0][2] for b in row]
    assert "Dashboard" not in labels_startup

    # Setelah login & attach orch baru -> tombol farming
    connected_orch = SimpleNamespace(
        bot=SimpleNamespace(current_map="oaklore-1", server=SimpleNamespace(name="DemoServer"), level=100),
        farming=SimpleNamespace(combat=None, auto_planner=None, is_leveling=lambda: False),
    )
    control.attach(connected_orch)
    control.handle_message(_message("/panel"))
    labels_connected = [b["text"] for row in transport.sent[1][2] for b in row]
    assert "Dashboard" in labels_connected
    assert "Combat" in labels_connected
