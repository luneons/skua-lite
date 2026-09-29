"""Unit test loop planning / auto goals."""
from unittest.mock import Mock

from skua_lite.auto_planner import AutoPlanner, AutoGoal, AutoGoalParser


def test_auto_planner_executes_goal_and_reports_status():
    bot = Mock()
    bot.state.value = "IN_MAP"
    planner = AutoPlanner(bot)

    # Contoh goal: farming "Water Draconian" sampai inventory punya "Draconian Scale" 10
    goal = AutoGoal(
        kind="drop",
        target_name="Water Draconian",
        drop_name="Draconian Scale",
        quantity=10,
    )
    planner.set_goal(goal)
    assert planner.current_goal is goal
    assert planner.active is True

    # Saat masih aktif, status harus melaporkan tujuannya
    status = planner.status()
    assert "Mencari Draconian Scale" in status

    planner.stop()
    assert planner.active is False


def test_auto_goal_parser_reads_drop_sentence():
    goal = AutoGoalParser.parse("auto cari Draconian Scale x5 dari Water Draconian")
    assert goal is not None
    assert goal.kind == "drop"
    assert "Draconian Scale" in goal.drop_name
    assert goal.quantity == 5
    assert "Water Draconian" in goal.target_name


def test_auto_goal_parser_reads_quest_sentence():
    goal = AutoGoalParser.parse("auto selesaikan quest 2260")
    assert goal is not None
    assert goal.kind == "quest"
    assert goal.target_name == "2260"


def test_auto_goal_parser_reads_generic_farm():
    goal = AutoGoalParser.parse("auto farming Water Draconian")
    assert goal is not None
    assert goal.kind == "farm"
    assert "Water Draconian" in goal.target_name


def test_auto_goal_parser_returns_none_for_garbage():
    assert AutoGoalParser.parse("auto") is None
    assert AutoGoalParser.parse("auto beli donat") is None
    assert AutoGoalParser.parse("bukan auto sama sekali") is None


def test_planner_stop_while_no_goal_is_safe():
    planner = AutoPlanner(Mock())
    planner.stop()  # must not raise
    assert planner.active is False
    assert planner.current_goal is None


def test_planner_replaces_previous_goal():
    planner = AutoPlanner(Mock())
    g1 = planner.set_goal(AutoGoal(kind="farm", target_name="Zombie"))
    g2 = planner.set_goal(AutoGoal(kind="drop", target_name="Skeleton", drop_name="Bone", quantity=2))
    assert planner.current_goal is g2
    assert planner.active is True
