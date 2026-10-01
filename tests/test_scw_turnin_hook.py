"""Test hook penolakan turn-in quest farming yang memicu eksekusi story Seven Circles."""
from unittest.mock import Mock
from skua_lite.bot import BotState
from skua_lite.farming import FarmingRuntime
from skua_lite.quest_state import QuestState


def test_farming_turnin_rejection_triggers_story_lock_and_redirects_to_sevencircles():
    """Saat quest farming 7979 ditolak ccqr karena prerequisite:
    - Runtime mendeteksi story lock
    - Leveling loop otomatis pindah ke sevencircles quest 7968
    - Tidak lagi farming di sevencircleswar sampai story selesai.
    """
    bot = Mock(username="mel e", session_user_id=1, room_id=42, level=35, state=BotState.IN_MAP)
    runtime = FarmingRuntime(bot=bot)
    
    # 1. Server terima acceptQuest 7979 & 7981
    runtime.feed_packet('{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7979,"msg":"success"}}}')
    runtime.feed_packet('{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7981,"msg":"success"}}}')
    
    # Karena 7981 accepted, spot awal adalah sevencircleswar
    spot1 = runtime.auto_level_spot()
    assert spot1 is not None
    assert spot1.map_name == "sevencircleswar"
    
    # 2. Server menolak turn-in 7979 karena prerequisite belum terpenuhi
    runtime.quest_state.note_turn_in_sent(7979)
    rejected_ccqr = '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":0,"QuestID":7979,"msg":"Must complete previous quest first"}}}'
    runtime.feed_packet(rejected_ccqr)
    
    # 3. Hook aktif: story locked, spot otomatis beralih ke sevencircles quest 7968
    assert runtime._scw_story_locked is True
    spot2 = runtime.auto_level_spot()
    assert spot2 is not None
    assert spot2.map_name == "sevencircles"
    assert spot2.quests == (7968,)
    assert runtime.leveling_dependency.quest_id == 7968
    
    # 4. Selesaikan 7968 -> next spot 7969
    runtime.feed_packet('{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":1,"QuestID":7968,"msg":"success"}}}')
    spot3 = runtime.auto_level_spot()
    assert spot3.map_name == "sevencircles"
    assert spot3.quests == (7969,)
    
    # 5. Selesaikan sampai gate quest 7977 -> lock terbuka, kembali ke sevencircleswar
    runtime.feed_packet('{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":1,"QuestID":7977,"msg":"success"}}}')
    assert runtime._scw_story_locked is False
    spot_final = runtime.auto_level_spot()
    assert spot_final.map_name == "sevencircleswar"
    assert spot_final.quests == (7979, 7980, 7981)
