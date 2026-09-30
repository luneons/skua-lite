"""Broaden local Wiki context and terminal answers to locations and quests."""
from __future__ import annotations

import json
import threading
import time

from skua_lite import cli
from skua_lite.ai_router import AIChatRouter
from skua_lite.agent_tools import AgentTools
from skua_lite.admin_commands import AdminCommandHandler
from skua_lite.wiki_knowledge import WikiKnowledge, build_wiki_database
from tests.test_wiki_knowledge import _source_dir


def _wiki(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    return WikiKnowledge(db)


def test_admin_lookup_commands_can_answer_quest_and_location(tmp_path):
    from unittest.mock import Mock

    wiki = _wiki(tmp_path)
    handler = AdminCommandHandler(tools=Mock(spec=AgentTools), wiki=wiki)

    loc = handler.handle("owner", "!quest Void Highlord's Challenge")
    quest = handler.handle("owner", "!shop Void Highlord's Challenge")

    assert "Roentgenium of Nulgath" in loc.reply
    assert "Roentgenium of Nulgath" in quest.reply


def test_admin_farm_suggest_returns_only_grounded_target_location(tmp_path):
    from unittest.mock import Mock

    wiki = _wiki(tmp_path)
    handler = AdminCommandHandler(tools=Mock(spec=AgentTools), wiki=wiki)

    hit = handler.handle("owner", "!farm Diabolical Warlord")
    miss = handler.handle("owner", "!farm Definitely Not A Monster")

    assert hit.consumed and "/join underworld" in hit.reply
    assert "Diabolical Warlord" in hit.reply
    assert "Tidak ada lokasi monster" in miss.reply


def test_farm_cli_dapat_routes_location_and_quest_queries(tmp_path, monkeypatch, capsys):
    wiki = _wiki(tmp_path)
    monkeypatch.setattr(cli, "_farm_wiki", lambda _orch: wiki)
    orch = type("Orch", (), {"bot": object(), "farming": object()})()

    assert cli.dispatch_farm(orch, "dapat", "Underworld dimana?") == "farm"
    location = capsys.readouterr().out
    assert "/join underworld" in location
    assert "Diabolical Warlord" in location

    assert cli.dispatch_farm(orch, "wiki", "Void Highlord's Challenge syaratnya apa?") == "farm"
    quest = capsys.readouterr().out
    assert "Roentgenium of Nulgath x15" in quest


def test_router_may_answer_location_question_from_local_wiki(tmp_path):
    wiki = _wiki(tmp_path)
    prompts: list[str] = []
    sent = threading.Event()
    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "cek wiki",
        send_chat=lambda _text: sent.set(),
        wiki_db_path=wiki.path,
    )
    router.handle_message("MELE AI ON", "mod")

    assert router.handle_message("Underworld join dimana?", "Player", sender_id=777)
    assert sent.wait(2)
    assert "KONTEKS WIKI AQW" in prompts[-1]
    assert "/join underworld" in prompts[-1]


def test_router_may_answer_quest_requirement_question_from_local_wiki(tmp_path):
    wiki = _wiki(tmp_path)
    prompts: list[str] = []
    sent = threading.Event()
    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "cek wiki",
        send_chat=lambda _text: sent.set(),
        wiki_db_path=wiki.path,
    )
    router.handle_message("MELE AI ON", "mod")

    assert router.handle_message(
        "Void Highlord's Challenge syaratnya apa?", "Player", sender_id=777
    )
    assert sent.wait(2)
    assert "KONTEKS WIKI AQW" in prompts[-1]
    assert "Roentgenium of Nulgath x15" in prompts[-1]


def test_wiki_location_router_context_still_skips_unrelated_questions(tmp_path):
    wiki = _wiki(tmp_path)
    prompts: list[str] = []
    sent = threading.Event()
    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "cek wiki",
        send_chat=lambda _text: sent.set(),
        wiki_db_path=wiki.path,
    )
    router.handle_message("MELE AI ON", "mod")

    assert router.handle_message("underworld conquer the map", "Player", sender_id=777) is False
    time.sleep(0.15)
    assert prompts == []
