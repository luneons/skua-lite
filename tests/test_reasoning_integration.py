"""Integration tests – reasoning bot: server rejection -> diagnosis -> auto-prerequisite execution."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from skua_lite.farming import FarmingRuntime
from skua_lite.quest_state import QuestState
from skua_lite.reasoning_engine import FailureKind


class TestFarmingReasoningIntegration:
    def test_rejected_accept_triggers_reasoning_and_sets_dependency(self):
        logs: list[str] = []
        bot = Mock()
        bot.room_id = 1
        bot.session_user_id = 100
        bot.username = "Hero"
        bot.level = 40
        bot.current_map = "sevencircleswar-100000"

        rt = FarmingRuntime(bot, on_log=logs.append)
        
        # Server menolak accept quest 7980 karena quest 7979 belum selesai
        reject_packet = (
            '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,'
            '"QuestID":7980,"msg":"You must complete the previous quest first."}}}'
        )
        rt.feed_packet(reject_packet)

        # 1. Pastikan log reasoning keluar dengan diagnosa dan solusi
        reason_logs = [l for l in logs if "[REASON]" in l]
        assert len(reason_logs) >= 1
        last_reason = reason_logs[-1]
        assert "7980" in last_reason
        assert "7968" in last_reason or "7969" in last_reason or "7979" in last_reason
        assert "syarat sebelumnya" in last_reason.lower() or "selesaikan quest" in last_reason.lower()

        # 2. Dependency leveling otomatis diarahkan ke prerequisite quest
        dep = rt.leveling_dependency
        assert dep is not None
        assert dep.quest_id < 7980

    def test_rejected_turn_in_logs_reasoning_honestly(self):
        logs: list[str] = []
        bot = Mock()
        bot.room_id = 1
        bot.session_user_id = 100
        bot.username = "Hero"
        bot.level = 80
        bot.current_map = "sevencircleswar-100000"

        rt = FarmingRuntime(bot, on_log=logs.append)
        
        # Server menolak turn-in karena item kurang
        ccqr_reject = (
            '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":0,'
            '"QuestID":7985,"msg":"You do not have the required items."}}}'
        )
        rt.feed_packet(ccqr_reject)

        reason_logs = [l for l in logs if "[REASON]" in l]
        assert len(reason_logs) >= 1
        assert "7985" in reason_logs[-1]
        assert "item" in reason_logs[-1].lower()
