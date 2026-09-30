from types import SimpleNamespace
from unittest.mock import Mock

from skua_lite import cli


def _orch(*, current_map="oaklore", leveling=False, auto=False, combat=False):
    goal = SimpleNamespace(kind="farm", target_name="Skeleton") if auto else None
    planner = SimpleNamespace(active=auto, current_goal=goal)
    state = SimpleNamespace(class_name="Mage", cell="r3")
    engine = SimpleNamespace(
        running=combat,
        target_name="Bone Berserker",
        state=state,
        map_wide=False,
        auto=False,
    )
    runtime = SimpleNamespace(
        running=True,
        combat=engine,
        auto_planner=planner,
        _leveling_target=80 if leveling else 0,
        _leveling_private=current_map.endswith("-100000"),
        is_leveling=lambda: leveling,
    )
    bot = SimpleNamespace(
        username="alice",
        server=SimpleNamespace(name="Yorumi"),
        current_map=current_map,
        room_id=42,
        state=SimpleNamespace(value="IN_MAP"),
        level=35,
        is_afk=False,
    )
    return SimpleNamespace(bot=bot, farming=runtime)


def test_farm_dashboard_surfaces_scope_location_character_and_active_task():
    lines = cli.farm_dashboard_lines(_orch(leveling=True, combat=True))
    text = "\n".join(lines)

    assert "PUBLIC" in text
    assert "oaklore / r3" in text
    assert "Level 35" in text
    assert "Mage" in text
    assert "LEVELING" in text
    assert "35 -> 80" in text
    assert "COMBAT ON" in text


def test_farm_dashboard_marks_private_room_and_auto_goal():
    text = "\n".join(cli.farm_dashboard_lines(_orch(
        current_map="oaklore-100000", auto=True,
    )))

    assert "PRIVATE" in text
    assert "AUTO FARM" in text
    assert "Skeleton" in text


def test_farm_prompt_is_short_and_contextual():
    assert cli.farm_prompt(_orch()) == "[PUBLIC | oaklore/r3 | IDLE] > "
    assert cli.farm_prompt(_orch(current_map="oaklore-100000", combat=True)) == (
        "[PRIVATE | oaklore/r3 | COMBAT] > "
    )


def test_farm_help_is_grouped_and_keeps_private_rule(capsys):
    cli.print_farm_help()
    output = capsys.readouterr().out

    assert "MULAI CEPAT" in output
    assert "NAVIGASI" in output
    assert "PERTARUNGAN" in output
    assert "PERLENGKAPAN" in output
    assert "Tanpa -private = room publik" in output


def test_dot_help_and_dashboard_are_farming_commands():
    assert cli.parse_farm_command(".help") == ("help", "")
    assert cli.parse_farm_command(".dashboard") == ("dashboard", "")
    assert cli.parse_farm_command(".ui") == ("dashboard", "")


def test_dashboard_dispatch_renders_dashboard(capsys):
    orch = _orch()

    assert cli.dispatch_farm(orch, "dashboard", "") == "farm"
    assert "FARMING DASHBOARD" in capsys.readouterr().out
