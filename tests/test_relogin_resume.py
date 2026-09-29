"""Self-healing reconnect test suites.

Asserts bounded backoff instead of infinite hammering, and asserts that goal,
target map, and follow mode survive the lifecycle tear-down.
"""
from unittest.mock import Mock
import pytest

from skua_lite.bot import BotState, BotError
from skua_lite.follow import OwnerFollower
from skua_lite.mode import RunMode
from skua_lite.runner import Orchestrator, ReloginWatcher
from skua_lite.reconnect import ReconnectPolicy
from skua_lite.farming import FarmingRuntime
from skua_lite.auto_planner import AutoGoal


def _mock_orch(mode=RunMode.FARMING):
    store = Mock()
    store.load.return_value = ("u", "p")
    orch = Orchestrator(target_map="yulgar-1", store=store, mode=mode)
    orch.bot = Mock()
    orch.bot.state = BotState.DISCONNECTED_BY_SERVER
    orch.bot.current_map = "bloodtitan-9999"
    
    orch.connect = Mock()
    orch.log = Mock()
    return orch


def test_relogin_watcher_respects_backoff_policy_and_gives_up():
    orch = _mock_orch()
    orch.restart = Mock(side_effect=BotError("gagal mock"))
    
    # Policy: max 3 attempts
    policy = ReconnectPolicy(base_delay=0.01, factor=2.0, max_delay=0.1, max_attempts=3)
    watcher = ReloginWatcher(orch, policy=policy)
    
    # Run synchronously to completion (since it should give up)
    watcher.run()
    
    assert orch.restart.call_count == 3
    # Check it logged giving up
    calls = orch.log.call_args_list
    assert any("menyerah" in str(c) for c in calls)


def test_relogin_joins_last_active_map_instead_of_default():
    orch = _mock_orch()
    orch.restart()
    
    # Connect must have been called. The target map should be the map the bot
    # was actually in, not the default map of the orchestrator.
    orch.connect.assert_called_once()
    assert orch.target_map == "bloodtitan-9999"


def test_relogin_preserves_active_farm_goal():
    orch = _mock_orch(mode=RunMode.FARMING)
    runtime = FarmingRuntime(bot=orch.bot)
    orch.farming = runtime
    goal = AutoGoal(kind="farm", target_name="Zombie")
    runtime.auto_planner.set_goal(goal)

    # connect() is what builds the replacement bot; simulate that swap.
    def _fake_connect(_u, _p):
        orch.bot = Mock()
        orch.bot.current_map = "zombie-1234"
        runtime.bot = orch.bot
        orch.bot.auto_planner = runtime.auto_planner

    orch.connect = Mock(side_effect=_fake_connect)
    orch.restart()

    assert runtime.auto_planner.active is True
    assert runtime.auto_planner.current_goal is goal


def test_relogin_restores_owner_follow_mode():
    orch = _mock_orch(mode=RunMode.ASSISTANT)
    orch.bot.ai_router = Mock(active_owner_id=123)
    orch.bot.follow = OwnerFollower()
    orch.bot.follow.start("mele", 123)

    def _fake_connect(_u, _p):
        orch.bot = Mock()
        orch.bot.current_map = "yulgar-14045"
        orch.bot.follow = OwnerFollower()

    orch.connect = Mock(side_effect=_fake_connect)
    orch.restart()

    assert orch.bot.follow.is_following is True
    assert orch.bot.follow.owner_name == "mele"
    assert orch.bot.follow.owner_id == 123


def test_relogin_restores_nothing_when_no_goal_or_follow_was_active():
    orch = _mock_orch(mode=RunMode.ASSISTANT)
    orch.bot.follow = OwnerFollower()

    def _fake_connect(_u, _p):
        orch.bot = Mock()
        orch.bot.current_map = "yulgar-14045"
        orch.bot.follow = OwnerFollower()

    orch.connect = Mock(side_effect=_fake_connect)
    orch.restart()

    # A fresh session must not inherit follow mode from nowhere.
    assert orch.bot.follow.is_following is False
    assert orch.bot.follow.owner_name == ""
