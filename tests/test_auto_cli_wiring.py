"""Integration between the CLI layer and the AutoPlanner.

The CLI loop creates the planner and wires its decisions to the runtime's I/O
methods (combat.attack, cli.move_to_cell, farming.get_drop, etc).
"""
import pytest
from unittest.mock import Mock, call

from skua_lite.auto_planner import AutoDecision, AutoGoal
from skua_lite.cli import dispatch_farm


def _mock_orch():
    orch = Mock()
    # Mock bot state
    orch.bot.state.value = "IN_MAP"
    orch.bot.is_afk = False
    orch.bot.room_id = 200
    
    # Mock runtime (farming/combat interface)
    runtime = Mock()
    runtime.combat.state.connected = True
    runtime.combat.state.monsters = {}
    orch.bot.farming = runtime

    # Stub the action router
    orch.bot.auto_planner = Mock()
    orch.bot.auto_planner.active = False
    return orch


def test_dispatch_farm_routes_auto_command_to_planner():
    orch = _mock_orch()
    
    # Simulate what cli.parse_farm_command("auto cari Bone x5 dari Skeleton") returns
    goal = AutoGoal(kind="drop", target_name="Skeleton", drop_name="Bone", quantity=5)
    result = dispatch_farm(orch, "auto", goal)
    
    assert result == "farm"
    
    # Did it route to the farming runtime?
    orch.farming.set_auto_goal.assert_called_once_with(goal)


def test_dispatch_farm_rejects_malformed_auto_command_and_does_not_set_goal():
    orch = _mock_orch()
    
    # User types: "auto"
    result = dispatch_farm(orch, "auto", "")
    
    assert result is None  # error parsed
    orch.bot.auto_planner.set_goal.assert_not_called()
