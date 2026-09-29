"""Decision-loop tests for the autonomous `.auto` planner.

The planner is a pure decision core: it observes a snapshot and returns the
next action. Threading/network stay outside so every branch is deterministic
and no test depends on timing.
"""
from unittest.mock import Mock

from skua_lite.auto_planner import (
    AutoDecision,
    AutoGoal,
    AutoObservation,
    AutoPlanner,
)


def _obs(**kwargs):
    base = dict(
        connected=True,
        enemies_in_cell=0,
        cells_with_enemies=(),
        drop_count=0,
        quest_ready=False,
    )
    base.update(kwargs)
    return AutoObservation(**base)


def _planner(goal=None):
    planner = AutoPlanner(Mock(), count_drop=lambda _goal: 0)
    if goal is not None:
        planner.set_goal(goal)
    return planner


def test_idle_when_no_goal_active():
    planner = _planner()
    assert planner.decide(_obs(enemies_in_cell=3)) == AutoDecision("idle")


def test_pauses_when_disconnected_instead_of_acting():
    planner = _planner(AutoGoal(kind="farm", target_name="Water Draconian"))
    assert planner.decide(_obs(connected=False, enemies_in_cell=2)) == AutoDecision("paused")


def test_attacks_enemies_present_in_current_cell():
    planner = _planner(AutoGoal(kind="farm", target_name="Water Draconian"))
    assert planner.decide(_obs(enemies_in_cell=2)) == AutoDecision("attack")


def test_moves_to_another_cell_when_current_cell_is_empty():
    planner = _planner(AutoGoal(kind="farm", target_name="Water Draconian"))
    decision = planner.decide(_obs(cells_with_enemies=("Boss", "Room2")))
    assert decision == AutoDecision("move", cell="Boss")


def test_waits_for_respawn_when_map_has_no_enemies_left():
    planner = _planner(AutoGoal(kind="farm", target_name="Water Draconian"))
    assert planner.decide(_obs()) == AutoDecision("wait", reason="menunggu respawn")


def test_drop_goal_completes_only_when_counter_reaches_quantity():
    goal = AutoGoal(kind="drop", target_name="Water Draconian", drop_name="Scale", quantity=5)
    planner = AutoPlanner(Mock(), count_drop=lambda _g: 4)
    planner.set_goal(goal)
    assert planner.decide(_obs(enemies_in_cell=1)) == AutoDecision("attack")

    planner = AutoPlanner(Mock(), count_drop=lambda _g: 5)
    planner.set_goal(goal)
    decision = planner.decide(_obs(enemies_in_cell=1))
    assert decision == AutoDecision("done", reason="Scaledrop tujuan tercapai")
    # A finished goal stops owning the bot.
    assert planner.active is False


def test_quest_goal_turns_in_only_when_server_says_ready():
    planner = _planner(AutoGoal(kind="quest", target_name="2260"))
    assert planner.decide(_obs(quest_ready=False, enemies_in_cell=1)) == AutoDecision("attack")

    planner = _planner(AutoGoal(kind="quest", target_name="2260"))
    decision = planner.decide(_obs(quest_ready=True))
    assert decision == AutoDecision("turn_in", quest_id=2260)
    assert planner.active is False


def test_loop_stops_calling_apply_after_goal_completes():
    goal = AutoGoal(kind="drop", target_name="X", drop_name="Y", quantity=1)
    applied: list[AutoDecision] = []
    planner = AutoPlanner(
        Mock(),
        count_drop=lambda _g: 1,
        apply=applied.append,
        observe=lambda: _obs(enemies_in_cell=1),
    )
    planner.set_goal(goal)

    planner.tick()
    planner.tick()

    # Exactly one decision was applied (the completion), then the loop idled.
    assert [d.action for d in applied] == ["done"]


def test_loop_applies_decisions_until_stopped():
    applied: list[AutoDecision] = []
    planner = AutoPlanner(
        Mock(),
        count_drop=lambda _g: 0,
        apply=applied.append,
        observe=lambda: _obs(enemies_in_cell=1),
    )
    planner.set_goal(AutoGoal(kind="farm", target_name="X"))

    assert planner.tick() is True
    assert planner.tick() is True
    planner.stop()
    assert planner.tick() is False
    assert [d.action for d in applied] == ["attack", "attack"]


def test_status_reports_decision_context():
    planner = _planner(AutoGoal(kind="farm", target_name="Water Draconian"))
    planner.decide(_obs(enemies_in_cell=1))
    assert "Water Draconian" in planner.status()
