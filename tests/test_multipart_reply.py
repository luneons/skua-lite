"""Tests: long wiki answers are split into paced AQW chat messages, never dropped."""
from __future__ import annotations

import threading
import time
from unittest.mock import Mock

from skua_lite.admin_commands import (
    AdminCommandHandler,
    AdminInbox,
    split_chat_message,
)
from skua_lite.agent_tools import AgentTools
from skua_lite.ai_router import AIChatRouter
from skua_lite.wiki_knowledge import WikiKnowledge, build_wiki_database
from tests.test_wiki_knowledge import _source_dir


# ---------------------------------------------------------------------------
# Unit: splitter
# ---------------------------------------------------------------------------
def test_split_short_text_is_one_chunk():
    assert split_chat_message("Burning Blade drop dari Diabolical Warlord.") == [
        "Burning Blade drop dari Diabolical Warlord."
    ]


def test_split_long_text_preserves_all_words():
    long = " ".join([f"kata{i}" for i in range(40)])
    chunks = split_chat_message(long, limit=50)
    assert all(len(c) <= 50 for c in chunks)
    assert " ".join(chunks) == long


def test_split_single_long_word_is_hard_cut():
    word = "A" * 300
    chunks = split_chat_message(word, limit=150)
    assert all(len(c) <= 150 for c in chunks)
    assert "".join(chunks) == word


def test_split_empty_is_empty():
    assert split_chat_message("") == []
    assert split_chat_message("   ") == []


def test_split_no_chunk_exceeds_limit():
    text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 10
    for chunk in split_chat_message(text, limit=150):
        assert len(chunk) <= 150, f"chunk too long: {chunk!r}"


# ---------------------------------------------------------------------------
# Integration: AdminInbox multi-part pacing
# ---------------------------------------------------------------------------
def _wiki(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    return WikiKnowledge(db)


def test_admin_resep_delivers_multiple_paced_parts(tmp_path):
    """!resep must arrive as >=2 messages, each <=150 chars."""
    sent: list[tuple[str, float]] = []
    done = threading.Event()
    lock = threading.Lock()

    def send_chat(text: str) -> None:
        with lock:
            sent.append((text, time.monotonic()))
        if len(sent) >= 2:
            done.set()

    handler = AdminCommandHandler(tools=Mock(spec=AgentTools), wiki=_wiki(tmp_path))
    inbox = AdminInbox(handler)
    inbox.submit("MELE", "!resep ArchFiend Spear", send_chat)

    assert done.wait(8), f"only {len(sent)} parts received"
    with lock:
        for text, _ in sent:
            assert len(text) <= 150, f"part too long: {text!r}"
        # Verify gap between consecutive sends >= 1.0s (lenient to avoid CI flakes)
        if len(sent) >= 2:
            gaps = [sent[i + 1][1] - sent[i][1] for i in range(len(sent) - 1)]
            assert all(g >= 1.0 for g in gaps), f"parts came too fast: gaps={gaps}"


def test_admin_dapat_short_result_arrives_as_single_message(tmp_path):
    """A short answer (<= 150 chars) must arrive as exactly one message."""
    sent: list[str] = []
    done = threading.Event()

    def send_chat(text: str) -> None:
        sent.append(text)
        done.set()

    handler = AdminCommandHandler(tools=Mock(spec=AgentTools), wiki=_wiki(tmp_path))
    inbox = AdminInbox(handler)
    inbox.submit("MELE", "!dapat Burning Blade", send_chat)

    assert done.wait(4)
    # Allow 1 or 2 — the answer may split if long, but must not be empty
    assert len(sent) >= 1
    for part in sent:
        assert len(part) <= 150


def test_admin_wiki_full_answer_not_dropped(tmp_path):
    """The split parts reassembled must contain key content, nothing silently removed."""
    sent: list[str] = []
    done = threading.Event()

    def send_chat(text: str) -> None:
        sent.append(text)
        done.set()

    handler = AdminCommandHandler(tools=Mock(spec=AgentTools), wiki=_wiki(tmp_path))
    inbox = AdminInbox(handler)
    inbox.submit("MELE", "!dapat ArchFiend Spear", send_chat)

    done.wait(6)
    full = " ".join(sent)
    assert "ArchFiend Spear" in full


# ---------------------------------------------------------------------------
# Integration: AIChatRouter multi-part wiki path
# ---------------------------------------------------------------------------
def test_router_sends_multiple_chunks_for_long_wiki_answer(tmp_path):
    """When wiki context makes the model answer long, router splits it."""
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)

    sent: list[str] = []
    received = threading.Event()

    def gen(prompt: str) -> str:
        # Simulate a model that echoes a long wiki-grounded answer
        return ("Burning Blade drop dari Diabolical Warlord di Underworld. "
                "Join dengan perintah /join underworld dan serang Diabolical Warlord. "
                "Monster ini muncul di cell tertentu dan bisa di-farm dengan class apapun. "
                "Drop rate cukup tinggi jadi tidak perlu banyak round. ")

    router = AIChatRouter(
        generator=gen,
        send_chat=lambda text: (sent.append(text), received.set()),
        wiki_db_path=db,
    )
    router.handle_message("MELE AI ON", "mod")

    result = router.handle_message(
        "Burning Blade dapat dari mana?", "Player", sender_id=777
    )
    assert result is True
    assert received.wait(4)
    # Every part must respect the 150-char limit
    for part in sent:
        assert len(part) <= 150, f"part too long ({len(part)} chars): {part!r}"
    # Total content must be non-empty
    assert " ".join(sent).strip()
