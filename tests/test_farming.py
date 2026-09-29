"""Tests for farming-mode packet builders and runtime (no AI, no Flash)."""
from __future__ import annotations

import struct
import threading
import time
import zlib
from unittest.mock import Mock

import pytest

from skua_lite import farming, sfs
from skua_lite.mode import RunMode
from tests.test_client import MockSFSServer


@pytest.fixture
def mock_server():
    srv = MockSFSServer()
    srv.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%alice%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":{"10":{"ItemID":10,"sName":"Mage","sType":"Class","sES":"co","bEquip":"1"}}}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"updateClass","uid":1,"sClassName":"Mage","ItemID":10}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"sAct","actions":{"active":[{"ref":"aa","nam":"Fireball","auto":true,"typ":"aa","tgt":"h","tgtMax":1,"cd":1800,"isOK":true},{"ref":"a4","nam":"Meteor","typ":"m","tgt":"h","tgtMax":3,"cd":12000,"isOK":true}]}}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair",'
        '"uoBranch":[{"uoName":"alice","uid":1,"strFrame":"Enter","intHP":900,"intHPMax":900,"intMP":300,"intMPMax":300,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Enter"}]}}}',
    ])
    srv.start()
    yield srv
    srv.stop()


def _wire(pkt: bytes) -> str:
    return pkt.rstrip(b"\x00").decode("latin-1")


def _swf_tag(code: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    if length < 63:
        return struct.pack("<H", (code << 6) | length) + payload
    return struct.pack("<HI", (code << 6) | 63, length) + payload


def _swf_bytes(labels: list[str]) -> bytes:
    body = b"\x08\x00" + b"\x00\x18" + struct.pack("<H", len(labels))
    for label in labels:
        body += _swf_tag(43, label.encode("utf-8") + b"\x00")
        body += _swf_tag(1)
    body += _swf_tag(0)
    payload = zlib.compress(body)
    return b"CWS" + bytes([10]) + struct.pack("<I", 8 + len(payload)) + payload


def test_get_drop_packet_wire_format():
    assert _wire(sfs.get_drop_packet(room=273, drop_id=9911)) == "%xt%zm%getDrop%273%9911%"


def test_rest_packet_sits_down_via_emotea_extension():
    assert _wire(sfs.rest_packet()) == "%xt%zm%emotea%1%rest%"


def test_rest_request_packet_repeats_rest_while_seated():
    assert _wire(sfs.rest_request_packet()) == "%xt%zm%restRequest%1%%"


def test_server_use_item_packet_wire_format():
    assert _wire(sfs.use_item_packet(room=273, item_id=1234)) == "%xt%zm%serverUseItem%273%+%1234%"


def test_sell_item_packet_wire_format():
    body = _wire(sfs.sell_item_packet(room=273, item_id=55, quantity=3, char_item_id=777))
    assert body == "%xt%zm%sellItem%273%55%3%777%"


def test_bank_packets_wire_format():
    assert _wire(sfs.load_bank_packet(room=273)) == "%xt%zm%loadBank%273%All%"
    body = _wire(sfs.bank_to_inventory_packet(room=273, item_id=11, char_item_id=22))
    assert body == "%xt%zm%bankToInv%273%11%22%"
    body = _wire(
        sfs.bank_swap_packet(room=273, inv_id=1, inv_char_id=2, bank_id=3, bank_char_id=4)
    )
    assert body == "%xt%zm%bankSwapInv%273%1%2%3%4%"


def test_try_quest_complete_packet_wire_format():
    body = _wire(
        sfs.try_quest_complete_packet(room=273, quest_id=101, reward_id=5, turn_ins="1,2")
    )
    assert body == "%xt%zm%tryQuestComplete%273%101%5%false%1,2%wvz%"


def test_aggro_mon_packet_wire_format():
    assert _wire(sfs.aggro_mon_packet(room=273, map_ids=[7, 9])) == "%xt%zm%aggroMon%273%7%9%"


def test_farming_profile_defaults_enable_verified_mage_attack():
    profile = farming.FarmProfile()
    assert profile.map_name == "lair-100000"
    assert profile.pickup_drops is True
    assert profile.rest_between_rounds is True
    assert profile.auto_attack is True
    assert profile.class_name == "Mage"
    assert profile.target_monster == "Water Draconian"


def test_farming_runtime_never_builds_ai_router():
    bot = Mock()
    bot.state = Mock()
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    assert runtime.ai_router is None
    assert getattr(bot, "ai_router", None) is None


def test_farming_runtime_rest_pickup_and_quest_use_verified_packets():
    sent: list[str] = []
    bot = Mock()
    bot.room_id = 273
    bot._send_raw = lambda pkt: sent.append(_wire(pkt))
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())

    runtime.rest()
    runtime.pickup_drop(9911)
    runtime.use_booster(1234)
    runtime.complete_quest(quest_id=101, reward_id=5, turn_ins="1,2")

    assert "%xt%zm%emotea%1%rest%" in sent
    assert "%xt%zm%getDrop%273%9911%" in sent
    assert "%xt%zm%serverUseItem%273%+%1234%" in sent
    assert "%xt%zm%tryQuestComplete%273%101%5%false%1,2%wvz%" in sent


def test_farming_runtime_attack_controls_combat_engine():
    class FakeCombat:
        running = False
        target_name = "Water Draconian"
        auto = False
        map_wide = False

        def set_auto(self, enabled):
            self.auto = bool(enabled)

        def set_map_wide(self, enabled):
            self.map_wide = bool(enabled)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

        def status(self):
            return "COMBAT ON"

    bot = Mock()
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    runtime.combat = FakeCombat()
    runtime.attack("Water Draconian")
    assert runtime.combat.running is True
    assert runtime.combat.auto is False
    assert runtime.combat.map_wide is False
    runtime.stop_attack()
    assert runtime.combat.running is False
    assert runtime.combat.map_wide is False
    assert runtime.combat_status() == "COMBAT ON"

    runtime.attack("auto")
    assert runtime.combat.running is True
    assert runtime.combat.auto is True
    assert runtime.combat.map_wide is False
    runtime.combat.target_name = "Water Draconian"

    with pytest.raises(ValueError):
        runtime.attack("Frogzard")


def test_farming_runtime_feeds_combat_and_captures_on_request(tmp_path):
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        combat_capture_path=tmp_path / "combat.log",
    )
    runtime.set_combat_capture(True)
    runtime.feed_packet('{"t":"xt","b":{"r":42,"o":{"cmd":"updateClass","uid":29185,"sClassName":"Mage"}}}')
    assert runtime.combat.state.class_name == "Mage"
    assert "updateClass" in (tmp_path / "combat.log").read_text(encoding="utf-8")


def test_farming_orchestrator_stays_active_and_joins_farm_map(mock_server, tmp_path, monkeypatch):
    """Farming mode: no AFK packet, no AI, and the farm map is the target."""
    from skua_lite import bot as bot_mod, credentials, login, runner, servers

    monkeypatch.setattr(
        login, "aqw_login",
        lambda u, p, *, timeout=20: login.LoginToken(username=u, token="TOK", success=True),
    )
    monkeypatch.setattr(
        servers, "fetch_server_list",
        lambda *, timeout=20: {"Yorumi": servers.Server(
            name="Yorumi", ip=mock_server.host, port=mock_server.port,
            online=True, full=False, upgrade_only=False,
        )},
    )
    # Even with AI configured, farming must not build the assistant stack.
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "test-key")
    monkeypatch.setenv("SKUA_AI_MODEL", "test-model")
    monkeypatch.setattr(
        runner, "openai_chat_generator",
        lambda _cfg: pytest.fail("farming mode must not build an AI generator"),
    )

    store = credentials.CredentialStore(base_dir=tmp_path)
    store.save("alice", "pw")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    orch = runner.Orchestrator(
        server_name="Yorumi", store=store, mode=RunMode.FARMING
    )
    orch.auto_relogin = False
    assert orch.target_map == "lair-100000"

    orch.connect("alice", "pw")
    assert orch.bot.state == bot_mod.BotState.IN_MAP
    assert orch.bot.ai_router is None
    assert orch.farming is not None and orch.farming.running is True
    assert orch.bot.is_afk is False

    orch.farming.pickup_drop(9911)
    time.sleep(0.2)
    assert any("%xt%zm%getDrop%42%9911%" in p for p in mock_server.received)
    assert not any("%xt%zm%cmd%42%afk%" in p for p in mock_server.received)

    # Combat state must be seeded by the handshake script itself.
    assert orch.farming.combat.state.class_name == "Mage"
    alive = orch.farming.combat.state.alive_monsters("Water Draconian")
    assert [monster.map_id for monster in alive] == [1]
    orch.farming.attack("Water Draconian")
    time.sleep(0.2)
    assert any("%xt%zm%gar%1%0%a4>m:1%wvz%" in p for p in mock_server.received)

    orch.shutdown()


def test_farm_cli_accepts_dot_prefix_and_auto_attack():
    from skua_lite import cli

    assert cli.parse_farm_command(".status") == ("status", "")
    assert cli.parse_farm_command(".") == ("status", "")
    assert cli.parse_farm_command(".join lair-100000") == ("join", "lair-100000")
    assert cli.parse_farm_command(".rest") == ("rest", "")
    assert cli.parse_farm_command(".combat") == ("combat", "")
    assert cli.parse_farm_command(".attack auto") == ("attack", "auto")
    assert cli.parse_farm_command(".attack off") == ("attack", "off")
    assert cli.parse_farm_command(".capture on") == ("capture", "on")
    assert cli.parse_farm_command(".chat /join lair-100000") == (
        "chat", "/join lair-100000"
    )
    assert cli.parse_farm_command(".chat /goto mele") == ("chat", "/goto mele")
    assert cli.parse_farm_command(".cells") == ("cells", "")
    assert cli.parse_farm_command(".cell Stairs") == ("cell", "Stairs")
    assert cli.parse_farm_command(".cell Cave BottomLeft") == (
        "cell", "Cave BottomLeft"
    )
    assert cli.parse_farm_command(".drop 9911") == ("drop", "9911")
    # Legacy `farm ...` spelling keeps working.
    assert cli.parse_farm_command("farm join yulgar") == ("join", "yulgar")
    assert cli.parse_farm_command(".say hi") == ("", "")
    assert cli.parse_farm_command("chat halo") == ("", "")

    calls: list[tuple[str, object]] = []

    class FakeRuntime:
        def attack(self, name=""):
            if str(name).strip().lower() == "auto":
                self.attack_auto()
                return
            calls.append(("attack", name))

        def attack_auto(self):
            calls.append(("attack_auto", None))

        def stop_attack(self):
            calls.append(("stop_attack", None))

        def rest(self):
            calls.append(("rest", None))

        def chat(self, message):
            calls.append(("chat", message))

        def move_to_cell(self, cell, pad=None):
            calls.append(("cell", (cell, pad)))

        def cell_scan_report(self):
            calls.append(("cells", None))
            return ["Enter [KAMU] (1 monster)", "Boss (0 monster)"]

        def combat_status(self):
            calls.append(("combat", None))
            return "ok"

    orch = Mock()
    orch.farming = FakeRuntime()

    cli.dispatch_farm(orch, "attack", "auto")
    cli.dispatch_farm(orch, "chat", "/goto mele")
    cli.dispatch_farm(orch, "cell", "Stairs")
    cli.dispatch_farm(orch, "cell", "Cave BottomLeft")
    cli.dispatch_farm(orch, "cells", "")
    cli.dispatch_farm(orch, "rest", "")
    cli.dispatch_farm(orch, "combat", "")
    cli.dispatch_farm(orch, "attack", "off")

    assert calls == [
        ("attack_auto", None),
        ("chat", "/goto mele"),
        ("cell", ("Stairs", None)),
        ("cell", ("Cave", "BottomLeft")),
        ("cells", None),
        ("rest", None),
        ("combat", None),
        ("stop_attack", None),
    ]


def test_farming_control_accepts_goal_sentence_not_only_commands():
    from skua_lite import cli

    assert cli.parse_farm_command("lawan semua musuh yang ada di map ini") == (
        "goal", "clear_map"
    )
    assert cli.parse_farm_command("Lawan semua musuh di map ini") == (
        "goal", "clear_map"
    )
    assert cli.parse_farm_command("berhenti lawan musuh") == ("goal", "stop")

    calls: list[str] = []

    class GoalRuntime:
        def fight_all_in_map(self):
            calls.append("clear_map")

        def stop_goal(self):
            calls.append("stop")

    orch = Mock(farming=GoalRuntime())
    cli.dispatch_farm(orch, "goal", "clear_map")
    cli.dispatch_farm(orch, "goal", "stop")
    assert calls == ["clear_map", "stop"]


def test_farming_runtime_map_goal_owns_combat_and_navigation():
    class GoalCombat:
        running = False
        map_wide = False

        def set_map_wide(self, enabled):
            self.map_wide = bool(enabled)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    logs: list[str] = []
    bot = Mock()
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot, profile=farming.FarmProfile(), on_log=logs.append
    )
    runtime.combat = GoalCombat()

    runtime.fight_all_in_map()
    assert runtime.combat.map_wide is True
    assert runtime.combat.running is True
    assert any("semua musuh" in line for line in logs)

    runtime.stop_goal()
    assert runtime.combat.map_wide is False
    assert runtime.combat.running is False


def test_farming_area_report_uses_shared_generation_snapshot():
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Enter"}]}}}'
    )

    rows = runtime.area_report()
    assert rows[0] == "area lair-100000 room 42 generation 1 [wire]"
    assert any("m:1 Water Draconian" in row for row in rows)
    assert runtime.area_json() == runtime.area_json()


def test_farming_cli_dispatches_area_human_and_json_reports(capsys):
    from skua_lite import cli

    assert cli.parse_farm_command(".area") == ("area", "")
    assert cli.parse_farm_command(".area json") == ("area", "json")

    class Runtime:
        def area_report(self):
            return ["area lair-1 room 42 generation 1 [wire]"]

        def area_json(self):
            return '{"schema_version":1}'

    orch = Mock(farming=Runtime())
    cli.dispatch_farm(orch, "area", "")
    cli.dispatch_farm(orch, "area", "json")
    out = capsys.readouterr().out
    assert "[AREA] area lair-1 room 42 generation 1 [wire]" in out
    assert '{"schema_version":1}' in out


def test_farming_runtime_scans_map_swf_cells_and_moves_between_them(tmp_path):
    from skua_lite.map_cells import MapCellScanner

    logs: list[str] = []
    scanned: list[str] = []

    def fetch(url, timeout):
        scanned.append(url)
        return _swf_bytes(["Enter", "Stairs", "Cave"])

    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    bot._send_raw = lambda pkt: sent.append(_wire(pkt))
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        on_log=logs.append,
        cell_scanner=MapCellScanner(cache_dir=tmp_path, fetch=fetch),
    )

    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )

    deadline = time.monotonic() + 10
    while not scanned and time.monotonic() < deadline:
        time.sleep(0.01)
    while (
        not runtime.combat.state.map_cells and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert scanned == ["https://game.aq.com/game/gamefiles/maps/lair-v1.swf"]
    assert runtime.cell_scan_report()[0].startswith("map lair-v1.swf")
    assert any("Stairs" in row for row in runtime.cell_scan_report())
    assert any("scan lair-v1.swf" in line for line in logs)

    runtime.move_to_cell("Stairs")
    assert sent == ["%xt%zm%moveToCell%42%Stairs%Left%"]

    # A second feed must not re-download the same map file.
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )
    assert len(scanned) == 1


def test_farming_runtime_keeps_observed_cells_when_swf_scan_fails():
    from skua_lite.map_cells import SWFCellError

    logs: list[str] = []

    def fetch(url, timeout):
        raise SWFCellError("bukan file SWF")

    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot, profile=farming.FarmProfile(), on_log=logs.append, cell_scanner=None
    )

    class FailingScanner:
        def scan(self, file_name):
            raise SWFCellError("bukan file SWF")

    runtime.cell_scanner = FailingScanner()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Boss"}]}}}'
    )

    report = runtime.cell_scan_report()
    assert report[0].startswith("scan server parsial")
    assert any(row.startswith("Enter [KAMU]") for row in report)
    assert any(row.startswith("Boss ") for row in report)
    assert any("scan SWF map gagal" in line for line in logs)


def test_farming_map_swf_scan_runs_in_background_and_never_truncates(tmp_path):
    from skua_lite.map_cells import MapCellScanner

    release = threading.Event()
    entered = threading.Event()

    def slow_fetch(url, timeout):
        assert timeout == url_timeout(url)
        entered.set()
        assert release.wait(timeout=10)
        return _swf_bytes([*[f"Cell{i:03d}" for i in range(60)], "Enter"])

    def url_timeout(url):
        from skua_lite.map_cells import DEFAULT_FETCH_TIMEOUT
        return DEFAULT_FETCH_TIMEOUT

    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        cell_scanner=MapCellScanner(cache_dir=tmp_path, fetch=slow_fetch),
    )

    entered.clear()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )

    # The packet thread returns while the download still runs.
    assert entered.wait(timeout=10)
    assert runtime.cell_scan_report()[0].startswith("scan server parsial")

    release.set()
    deadline = time.monotonic() + 10
    while (
        runtime.cell_scan_report()[0].startswith("scan server parsial")
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    report = runtime.cell_scan_report()
    assert report[0].startswith("map lair-v1.swf")
    assert len(report) == 1 + 61 + 1  # header + all cells + pad row
    assert any(row.startswith("Cell059 ") for row in report)
    assert rows_in_observed_order(report)


def rows_in_observed_order(report: list[str]) -> bool:
    enter = next(i for i, row in enumerate(report) if row.startswith("Enter [KAMU]"))
    first_cell = next(i for i, row in enumerate(report) if row.startswith("Cell000 "))
    return enter < first_cell


def test_farm_cli_parses_combat_capture_and_dispatches_commands():
    from skua_lite import cli

    assert cli.parse_farm_command("farm status") == ("status", "")
    assert cli.parse_farm_command("farm") == ("status", "")
    assert cli.parse_farm_command("farm join yulgar") == ("join", "yulgar")
    assert cli.parse_farm_command("farm attack Water Draconian") == ("attack", "Water Draconian")
    assert cli.parse_farm_command("farm capture on") == ("capture", "on")
    assert cli.parse_farm_command("chat halo") == ("", "")

    calls: list[tuple[str, object]] = []

    class FakeRuntime:
        def status(self):
            calls.append(("status", None))
            return "ok"

        def join(self, target):
            calls.append(("join", target))

        def complete_quest(self, quest_id, reward_id=-1, turn_ins=""):
            calls.append(("quest", (quest_id, reward_id, turn_ins)))

        def load_bank(self):
            calls.append(("bank", "load"))

        def sell(self, item_id, quantity, char_item_id):
            calls.append(("sell", (item_id, quantity, char_item_id)))

        def attack(self, target):
            calls.append(("attack", target))

        def set_combat_capture(self, enabled):
            calls.append(("capture", enabled))

    orch = Mock()
    orch.farming = FakeRuntime()

    cli.dispatch_farm(orch, "status", "")
    cli.dispatch_farm(orch, "join", "yulgar")
    cli.dispatch_farm(orch, "quest", "101 5 1,2")
    cli.dispatch_farm(orch, "bank", "load")
    cli.dispatch_farm(orch, "sell", "55 3 777")
    cli.dispatch_farm(orch, "attack", "Water Draconian")
    cli.dispatch_farm(orch, "capture", "on")

    assert calls == [
        ("status", None),
        ("join", "yulgar"),
        ("quest", (101, 5, "1,2")),
        ("bank", "load"),
        ("sell", (55, 3, 777)),
        ("attack", "Water Draconian"),
        ("capture", True),
    ]


def test_farming_orchestrator_connect_skips_ai_and_afk(monkeypatch):
    """connect() in farming mode never builds the assistant stack."""
    from skua_lite import runner

    monkeypatch.setattr(runner.AIConfig, "from_env", lambda: Mock(configured=True))
    monkeypatch.setattr(
        runner,
        "openai_chat_generator",
        lambda cfg: pytest.fail("farming mode must not build a generator"),
    )

    orch = runner.Orchestrator(mode=RunMode.FARMING)
    assert orch.mode is RunMode.FARMING

    built = {}

    class FakeBot:
        def __init__(self, **kwargs):
            built.update(kwargs)
            self.current_map = "battleon-100000"
            self.room_id = 3
            self.is_afk = False
            self.state = Mock(value="IN_MAP")
            self.ai_router = kwargs.get("ai_router")

        def start(self):
            self.state = Mock(value="IN_MAP")

    monkeypatch.setattr(runner.bot_mod, "AQWBot", FakeBot)
    monkeypatch.setattr(
        runner.login, "aqw_login", lambda u, p: Mock(username=u, token="t")
    )
    monkeypatch.setattr(
        runner.servers,
        "fetch_server_list",
        lambda: [Mock(name="Yorumi", ip="1.2.3.4", port=5588)],
    )
    monkeypatch.setattr(runner.servers, "pick", lambda lst, name: lst[0])
    orch.auto_relogin = False

    orch.connect("alice", "pw")
    assert built.get("ai_router") is None
    assert orch.farming is not None
    assert orch.farming.running is True
