"""Auto goal integration via owner chat."""
from unittest.mock import Mock

from skua_lite.bot import BotState
from skua_lite.auto_planner import AutoPlanner
from tests.test_follow import _follow_bot


def test_owner_can_issue_auto_goals_via_chat_if_planner_exists():
    b, router = _follow_bot()
    router.owner_arrived(21623, "mele")

    # Give the bot an active auto_planner (as FarmingRuntime does)
    planner = AutoPlanner(bot=b)
    b.auto_planner = planner

    # Owner issues a goal
    b._handle_server_packet(
        f"%xt%chatm%-1%zone~auto cari Bone x5 dari Skeleton%mele%21623%273%0%"
    )
    
    assert planner.active is True
    assert planner.current_goal is not None
    assert planner.current_goal.kind == "drop"
    assert planner.current_goal.drop_name == "Bone"


def test_non_owner_cannot_issue_auto_goals():
    b, router = _follow_bot()
    router.owner_arrived(21623, "mele")

    planner = AutoPlanner(bot=b)
    b.auto_planner = planner

    # Impostor tries to issue a goal
    b._handle_server_packet(
        f"%xt%chatm%-1%zone~auto cari Bone x5 dari Skeleton%impostor%9999%273%0%"
    )
    
    assert planner.active is False


def test_owner_berhenti_stops_the_active_goal():
    b, router = _follow_bot()
    router.owner_arrived(21623, "mele")
    planner = AutoPlanner(bot=b)
    b.auto_planner = planner

    b._handle_server_packet(
        f"%xt%chatm%-1%zone~auto cari Bone x5 dari Skeleton%mele%21623%273%0%"
    )
    assert planner.active is True

    # Owner says stop
    b._handle_server_packet(f"%xt%chatm%-1%zone~Berhenti%mele%21623%273%0%")
    assert planner.active is False
