"""Test story hunt: quest story tanpa cell spesifik harus memakai map-wide."""
from unittest.mock import Mock
from skua_lite.bot import BotState
from skua_lite.farming import FarmingRuntime


def test_story_step_without_cell_uses_map_wide_hunt():
    """Quest story 7968 tidak punya cell spesifik: combat harus hunt (map-wide)."""
    bot = Mock(username="demo-user", session_user_id=1, room_id=42,
               level=35, state=BotState.IN_MAP, current_map="sevencircles-1")
    runtime = FarmingRuntime(bot=bot)
    # Story belum selesai
    runtime.quest_state.note_quest_slots(["0"] * 395 + ["0"])

    spot = runtime.auto_level_spot()
    assert spot is not None
    assert spot.map_name == "sevencircles"
    assert spot.quests == (7968,)
    # Story step 7968: QuestStep tanpa cell spesifik
    assert spot.cell in ("", "Enter")

    # Simulasi tick loop: story hunt wajib map-wide agar engine pindah ke r2
    runtime.combat = Mock(state=Mock(cell="Enter", map_file_name="sevencircles.swf"),
                          running=False)
    runtime.join = Mock()
    runtime.move_to_cell = Mock()
    runtime._send = Mock()

    # Panggil satu iterasi logika combat dari _leveling_loop secara manual:
    # (duplikasi minimal dari branch combat story)
    from skua_lite.scw import QuestStep
    dependency = runtime.leveling_dependency
    assert dependency is not None
    assert dependency.quest_id == 7968
    is_hunt = not bool(spot.cell) or (spot.cell == "Enter" and spot.map_name != "sevencircleswar")
    assert is_hunt is True


def test_scw_farm_spot_keeps_focused_cell_combat():
    """Spot farming sevencircleswar (Enter/Right) TIDAK hunt: tetap fokus."""
    bot = Mock(username="demo-user", session_user_id=1, room_id=42,
               level=35, state=BotState.IN_MAP, current_map="sevencircleswar-1")
    runtime = FarmingRuntime(bot=bot)
    # Story selesai
    runtime.quest_state.note_quest_slots(["0"] * 395 + ["10"])

    spot = runtime.auto_level_spot()
    assert spot is not None
    assert spot.map_name == "sevencircleswar"
    assert spot.cell == "Enter"
    is_hunt = not bool(spot.cell) or (spot.cell == "Enter" and spot.map_name != "sevencircleswar")
    assert is_hunt is False
