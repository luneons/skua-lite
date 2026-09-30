"""Wiring tests: admin `!dapat`, farming `.dapat`, router wiki context."""
from __future__ import annotations

import json
import threading
import time

from skua_lite import cli
from skua_lite.admin_commands import AdminCommandHandler
from skua_lite.agent_tools import AgentTools
from skua_lite.ai_router import AIChatRouter
from skua_lite.wiki_knowledge import WikiKnowledge, build_wiki_database
from tests.test_wiki_knowledge import _source_dir


def _wiki(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    return WikiKnowledge(db)


def test_admin_dapat_answers_from_local_db_without_web(tmp_path):
    from unittest.mock import Mock

    tools = Mock(spec=AgentTools)
    handler = AdminCommandHandler(tools=tools, wiki=_wiki(tmp_path))

    outcome = handler.handle("MELE", "!dapat Burning Blade")

    assert outcome.consumed is True
    assert "Diabolical Warlord" in outcome.reply
    assert len(outcome.reply) <= 150
    tools.web_search.assert_not_called()


def test_admin_dapat_without_db_falls_back_to_help_text(tmp_path):
    from unittest.mock import Mock

    tools = Mock(spec=AgentTools)
    handler = AdminCommandHandler(
        tools=tools, wiki=WikiKnowledge(tmp_path / "missing.db")
    )

    outcome = handler.handle("MELE", "!dapat Burning Blade")

    assert outcome.consumed is True
    assert outcome.reply


def test_farm_cli_parses_dapat_and_wiki():
    assert cli.parse_farm_command(".dapat Burning Blade") == (
        "dapat", "Burning Blade",
    )
    assert cli.parse_farm_command(".wiki VHL") == ("wiki", "VHL")


def test_router_attaches_wiki_context_for_source_question(tmp_path):
    prompts: list[str] = []
    sent = threading.Event()
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)

    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "oke",
        send_chat=lambda _text: sent.set(),
        wiki_db_path=db,
    )
    router.handle_message("MELE AI ON", "mod")
    prompts.clear()

    assert router.handle_message(
        "Burning Blade dapat dari mana?", "Player", sender_id=777
    ) is True
    assert sent.wait(1)
    assert prompts and "KONTEKS WIKI AQW" in prompts[-1]
    assert "Diabolical Warlord" in prompts[-1]


def test_router_skips_wiki_context_for_unrelated_chat(tmp_path):
    prompts: list[str] = []
    sent = threading.Event()
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)

    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "oke",
        send_chat=lambda _text: sent.set(),
        wiki_db_path=db,
    )
    router.handle_message("MELE AI ON", "mod")
    prompts.clear()

    assert router.handle_message(
        "bro ada yang punya link discord ga?", "Player", sender_id=777
    ) is False
    time.sleep(0.2)
    assert prompts == []


def test_public_wiki_command_works_for_non_owner_even_during_owner_lock(tmp_path):
    from skua_lite.admin_commands import AdminCommandHandler

    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    sent: list[str] = []
    done = threading.Event()
    handler = AdminCommandHandler(tools=AgentTools(tmp_path), wiki=WikiKnowledge(db))
    router = AIChatRouter(
        generator=lambda _text: "should not invoke model",
        send_chat=lambda text: (sent.append(text), done.set()),
        admin_handler=handler,
    )
    router.owner_arrived(21623)
    assert done.wait(2)
    sent.clear()
    done.clear()

    assert router.handle_message("!dapat Burning Blade", "Player", sender_id=777) is True
    assert done.wait(2)
    assert "Diabolical Warlord" in sent[-1]


def test_public_wiki_commands_do_not_grant_other_admin_tools(tmp_path):
    from unittest.mock import Mock

    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    sent: list[str] = []
    done = threading.Event()
    tools = Mock(spec=AgentTools)
    handler = AdminCommandHandler(tools=tools, wiki=WikiKnowledge(db))
    router = AIChatRouter(
        generator=lambda _text: "should not invoke model",
        send_chat=lambda text: (sent.append(text), done.set()),
        admin_handler=handler,
    )
    router.owner_arrived(21623)
    assert done.wait(2)
    done.clear()

    assert router.handle_message("!cari info", "Player", sender_id=777) is False
    assert router.handle_message("!exec print(1)", "Player", sender_id=777) is False
    tools.web_search.assert_not_called()
    tools.run_code.assert_not_called()
    assert not done.wait(0.2)
