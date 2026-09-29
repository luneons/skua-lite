import threading
import time
from pathlib import Path
from unittest.mock import Mock

from skua_lite.ai_router import (
    AIChatRouter,
    AIConfig,
    _safe_non_owner_reply,
    _safe_reply,
    mentions_mele,
    _GREETING_TEMPLATES,
)


def test_regular_arrival_greetings_rotate_through_requested_variants():
    sent: list[str] = []
    router = AIChatRouter(generator=Mock(), send_chat=sent.append)

    for _ in range(len(_GREETING_TEMPLATES)):
        assert router.user_arrived("Alice") is True

    assert sent == [
        "Halo Alice",
        "Woy Alice",
        "Oitt Alice baru dateng.",
        "Yoo! Alice my gang!",
        "Wew ada si Alice",
        "Lahh itukan si Alice",
        "Kok ada Alice disini",
        "Yaelah Alice lagi",
        "Hai sayangku Alice baru datang.",
    ]


def test_arrival_greeting_rotation_wraps_and_respects_150_chars():
    sent: list[str] = []
    router = AIChatRouter(generator=Mock(), send_chat=sent.append)
    long_name = "A" * 200

    for _ in range(len(_GREETING_TEMPLATES) + 1):
        assert router.user_arrived(long_name) is True

    assert sent[0].startswith("Halo ")
    assert sent[-1] == sent[0]
    assert all(len(text) <= 150 for text in sent)


def test_safe_reply_strips_internal_research_and_bracket_markers():
    leaked = "Data belum ada. RESEARCH: https://aqwwiki.wikidot.com/stonecrusher_enchantments"
    assert "RESEARCH" not in _safe_reply(leaked)
    assert "http" not in _safe_reply(leaked).lower()

    internal = "[INTERNAL: No local data for SC enchantments; prior RESEARCH query pending]"
    assert "INTERNAL" not in _safe_reply(internal).upper()


def test_safe_reply_strips_internal_marker_for_non_owner_path():
    leaked = "[INTERNAL: prior RESEARCH query pending] data tak ada"
    assert "INTERNAL" not in _safe_non_owner_reply(leaked).upper()
    assert "RESEARCH" not in _safe_non_owner_reply(leaked).upper()


def test_ultra_guide_loader_finds_and_summarizes_darkon():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    assert guide.boss_names
    darkon = guide.section("ultradarkon")
    assert darkon
    assert "StoneCrusher" in darkon
    assert "LightCaster" in darkon
    assert any(guide.source_files)  # loaded from panduan/*.md


def test_ultra_guide_loader_finds_and_summarizes_dage():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    dage = guide.section("ultradage")
    assert dage
    assert "Ultra Dage" in dage
    assert any("ultradage" in source.lower() for source in guide.source_files)
    # A mechanic question retrieves the Noxious Decay section, not the setup dump.
    mechanic = guide.context_for("noxious decay ultra dage gimana")
    assert "Noxious Decay" in mechanic
    assert "Ultra Dage" in mechanic


def test_ultra_guide_discovers_all_markdown_files():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    assert len(guide.source_files) >= 6
    assert any("grimchallenge" in source.lower() for source in guide.source_files)
    assert any("ultragramiel" in source.lower() for source in guide.source_files)


def test_ultra_guide_retrieves_relevant_sections_for_mechanic_question():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    context = guide.context_for("noxious decay ultra dage gimana cara handle")
    assert context
    assert "Noxious Decay" in context
    # Section that mentions protection circle should be selected, not the
    # full setup dump.
    assert "Ultra Dage" in context


def test_ultra_guide_finds_overfiend_blade_for_nulgath_question():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    context = guide.context_for("cara handle overfiend blade ultra nulgath")
    assert context
    assert "Overfiend" in context
    assert "Ultra Nulgath" in context


def test_ultra_guide_no_match_for_unrelated_question():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    assert guide.context_for("link discord bro") == ""


def test_router_attaches_ultra_knowledge_when_question_asks_about_ultra():
    prompts = []

    def generate(message):
        prompts.append(message)
        return "oke"

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.owner_arrived(21623)
    # Let the arrival greeting finish so the next prompt is the real question.
    time.sleep(0.2)
    prompts.clear()

    assert router.handle_message(
        "bro cara ngelawan ultra dage gimana?", "MELE", sender_id=21623
    ) is True
    time.sleep(0.3)
    assert prompts
    combined = str(prompts[-1])
    assert "Noxious Decay" in combined
    assert "Ultra Dage" in combined


def test_router_does_not_attach_ultra_knowledge_for_unrelated_questions():
    prompts = []

    def generate(message):
        prompts.append(message)
        return "oke"

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.owner_arrived(21623)
    time.sleep(0.2)
    prompts.clear()

    assert router.handle_message(
        "bro ada yang punya link discord ga?", "MELE", sender_id=21623
    ) is True
    time.sleep(0.3)
    assert prompts
    combined = str(prompts[-1]).lower()
    assert "ultradage" not in combined
    assert "ultradarkon" not in combined


def test_router_reloads_ultra_guides_added_after_startup(tmp_path):
    prompts = []
    sent = threading.Event()
    guide_dir = tmp_path / "panduan"
    guide_dir.mkdir()

    router = AIChatRouter(
        generator=lambda message: prompts.append(message) or "oke",
        send_chat=lambda _text: sent.set(),
        guide_dir=guide_dir,
    )
    router.handle_message("MELE AI ON", "mod")
    (guide_dir / "ultrafoo.md").write_text(
        "# Ultra Foo\n## Special Mechanic\nGunakan Moon Shield saat Foo Burst.",
        encoding="utf-8",
    )

    assert router.handle_message(
        "cara lawan ultra foo?", "Player", sender_id=777
    ) is True
    assert sent.wait(1)
    assert prompts and "Moon Shield" in prompts[-1]
    assert "Ultra Foo" in prompts[-1]


def test_non_owner_ultra_question_is_answered_without_mele_mention():
    prompts = []
    sent = threading.Event()

    def generate(message):
        prompts.append(message)
        return "Dage memakai Noxious Decay."

    router = AIChatRouter(
        generator=generate,
        send_chat=lambda _text: sent.set(),
    )
    router.handle_message("MELE AI ON", "mod")

    assert router.handle_message(
        "ultra dage pakai mechanic apa?", "Player", sender_id=777
    ) is True
    assert sent.wait(1)
    assert prompts and "Ultra Dage" in prompts[-1]


def test_router_strips_md_source_filenames_from_chat_replies():
    prompts = []
    sent = []
    done = threading.Event()

    def generate(message):
        prompts.append(message)
        return "Gunakan Noxious Decay (sumber: ultra/ultradage.md). Hindari mati."

    router = AIChatRouter(
        generator=generate,
        send_chat=lambda text: (sent.append(text), done.set()),
    )
    router.handle_message("MELE AI ON", "mod")
    assert router.handle_message(
        "cara lawan ultra dage?", "Player", sender_id=777
    ) is True
    assert done.wait(1)
    # The chat that was sent to the game must not contain the .md filename or
    # the "sumber:" prefix because AQW chat is capped at ~150 chars.
    last = sent[-1]
    assert "ultradage.md" not in last
    assert "sumber:" not in last.lower()
    assert "Noxious Decay" in last


def test_context_window_for_named_boss_includes_mechanic_and_setup(tmp_path):
    from skua_lite.ultra_guide import UltraGuide

    base = tmp_path / "panduan"
    base.mkdir()
    (base / "ultradage.md").write_text(
        "# Ultra Dage\n"
        + "\n\n".join(
            f"## {title}\n" + ("lorem ipsum. " * depth)
            for title, depth in (
                ("Noxious Decay", 30),
                ("Protection Circle", 25),
                ("Party Composition", 40),
                ("Standard 4-Class Setup", 35),
                ("Common Mistakes", 20),
                ("TL;DR", 5),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    guide = UltraGuide.discover(base)
    context = guide.context_for("cara handle noxious decay ultra dage")
    # Both the mechanic (Noxious Decay) and the setup sections should be in
    # the prompt so the AI can answer without missing the standard recipe.
    assert "Noxious Decay" in context
    assert "Standard 4-Class Setup" in context or "Party Composition" in context
    # Section bodies should not be truncated to a single sentence.
    assert len(context) >= 1200


def test_context_window_caps_total_prompt_size(tmp_path):
    from skua_lite.ultra_guide import UltraGuide

    base = tmp_path / "panduan"
    base.mkdir()
    huge_body = ("Bagian penting. " * 200)
    (base / "ultraspeaker.md").write_text(
        "# Ultra Speaker\n## Truth\n" + huge_body
        + "\n\n## Listen\n" + huge_body
        + "\n\n## Equal\n" + huge_body
        + "\n",
        encoding="utf-8",
    )

    guide = UltraGuide.discover(base)
    context = guide.context_for("cara handle truth listen equal ultra speaker")
    # Even when all sections are huge the prompt must stay bounded so the
    # API call doesn't get rejected.
    assert len(context) <= 8000


def test_generic_ultra_question_gets_index_for_all_loaded_guides():
    from skua_lite.ultra_guide import UltraGuide

    guide = UltraGuide.discover(Path(__file__).resolve().parents[1] / "panduan")
    context = guide.context_for("info ultra dong")
    assert context
    assert "ultradage.md" in context.lower()
    assert "ultranulgath.md" in context.lower()
    assert "ultraspeaker.md" in context.lower()
    assert "ultragramiel.md" in context.lower()
    assert "grimchallenge.md" in context.lower()


def test_mele_mentions_match_whole_words_only():
    assert mentions_mele("le lagi ngapain?")
    assert mentions_mele("eh ada lu juga mel")
    assert mentions_mele("MELE, sini dong")
    assert not mentions_mele("legend banget")
    assert not mentions_mele("melodi lagu")


def test_owner_arrival_forces_lock_and_sends_greeting():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "selamat datang!", send_chat=send)

    assert router.owner_arrived(21623) is True
    assert done.wait(2)
    assert router.enabled is True
    assert router.owner_lock is True
    assert sent == ["Master, selamat datang!"]


def test_duplicate_owner_arrival_does_not_send_greeting_twice():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "hai!", send_chat=send)
    router.owner_arrived(21623)
    assert done.wait(2)
    done.clear()
    router.owner_arrived(21623)
    time.sleep(0.1)
    assert len(sent) == 1


def test_owner_arrival_from_second_account_greets_as_owner_too():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "hai!", send_chat=send)
    assert router.owner_arrived(21631) is True
    assert done.wait(2)
    assert sent == ["Master, hai!"]


def test_real_me_le_uid_23461_is_recognized_as_owner():
    """The owner's UID on the live server can drift to a new value; the
    router must still recognise the account by display name as a fallback."""
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "selamat datang", send_chat=send)
    # UID 23461 is the live "me le" UID observed in presence_capture.log
    # and is not yet in the hard-coded _OWNER_IDS table.
    assert router.owner_arrived(23461, "me le") is True
    assert done.wait(2)
    assert router.owner_lock is True
    assert router.active_owner_id == 23461
    assert sent == ["Master, selamat datang"]
    # Subsequent lock checks use the observed dynamic UID.
    assert router.active_owner_id != 22422


def test_real_me_le_uid_is_recognized_as_owner():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "selamat datang", send_chat=send)
    assert router.owner_arrived(22422) is True
    assert done.wait(2)
    assert router.owner_lock is True
    assert router.active_owner_id == 22422
    assert sent == ["Master, selamat datang"]


def test_room_log_feeds_owner_question_with_chat_and_presence():
    prompts = []
    sent = []
    done = threading.Event()

    def generate(message):
        prompts.append(message)
        return "Alice sama Bob bahas farm. Alice masuk, Bob keluar."

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=generate, send_chat=send)
    router.note_presence("masuk", "Alice", 11)
    router.note_chat("Alice", "farm di yulgar lagi rame")
    router.note_presence("keluar", "Bob", 22)
    router.note_chat("Bob", "aku cabut dulu")

    router.owner_arrived(21631)
    assert done.wait(2)
    sent.clear()
    done.clear()
    prompts.clear()

    assert router.handle_message(
        "ada apa ini? siapa yang keluar masuk?", "ME LE", sender_id=21631
    ) is True
    assert done.wait(2)
    assert "Alice" in prompts[-1]
    assert "Bob" in prompts[-1]
    assert "farm" in prompts[-1]
    assert "keluar" in prompts[-1]
    assert "tuan" not in sent[-1].lower()


def test_room_log_is_not_attached_to_non_owner_replies():
    prompts = []

    def generate(message):
        prompts.append(message)
        return "ada"

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.note_chat("Alice", "rahasia farm")
    router.handle_message("MELE AI ON", "mod")
    assert router.handle_message("le apa kabar", "stranger", sender_id=9) is True
    time.sleep(0.2)
    assert prompts
    assert "rahasia farm" not in prompts[-1]


def test_owner_account_aliases_are_matched_exactly():
    from skua_lite.ai_router import is_owner_account

    assert is_owner_account("ME LE")
    assert is_owner_account("mele")
    assert not is_owner_account("Sorani Ex")
    assert not is_owner_account("notmele")
    assert not is_owner_account("Sorani Extra")


def test_owner_is_greeted_once_when_presence_packet_arrives_even_if_ai_was_off():
    sent = []
    done = threading.Event()
    generated = []

    def generate(message):
        generated.append(message)
        return "selamat datang lagi"

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=generate, send_chat=send)
    assert router.enabled is False
    assert router.owner_arrived(21623) is True
    assert done.wait(2)
    assert router.enabled is True
    assert router.owner_lock is True
    assert sent == ["Master, selamat datang lagi"]

    # Duplicate retrieveUserData must not greet twice.
    assert router.owner_arrived(21623) is True
    time.sleep(0.1)
    assert len(generated) == 1


def test_owner_chat_reply_is_not_double_addressed():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "siap, aku dengerin", send_chat=send)
    router.owner_arrived(21631)
    assert done.wait(2)
    sent.clear()
    done.clear()
    assert router.handle_message("ada di sini", "ME LE") is True
    assert done.wait(2)
    # Owner replies must NEVER be prefixed with "Tuan Mele"; the AI greeting
    # at arrival is the only place that phrase is allowed, and even there we
    # avoid double-prefixing when the reply already starts with it.
    assert sent == ["siap, aku dengerin"]


def test_owner_chat_reply_keeps_ai_text_verbatim_without_reinserting_title():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(
        generator=lambda _message: "oke bosku langsung gas", send_chat=send
    )
    router.owner_arrived(21623)
    assert done.wait(2)
    sent.clear()
    done.clear()
    assert router.handle_message("mel kerjain", "MELE") is True
    assert done.wait(2)
    assert sent == ["oke bosku langsung gas"]
    assert all(not line.lower().startswith("tuan mele") for line in sent)


def test_owner_arrival_greeting_does_not_double_prefix_when_ai_already_uses_title():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    # AI sometimes greets with the title already in its reply.
    router = AIChatRouter(
        generator=lambda _message: "Tuan Mele, ada yang bisa dibantu?", send_chat=send
    )
    assert router.owner_arrived(21623) is True
    assert done.wait(2)
    assert sent == ["Master, ada yang bisa dibantu?"]


def test_owner_is_greeted_even_without_trigger_and_reply_is_not_prefixed():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "siap, aku dengerin", send_chat=send)
    router.handle_message("MELE AI ON", "moderator")
    assert router.handle_message("ada di sini", "ME LE") is True
    assert done.wait(2)
    assert sent == ["siap, aku dengerin"]


def test_ai_turns_off_when_owner_leaves_location_and_resets_defaults():
    router = AIChatRouter(generator=Mock(return_value="hai"), send_chat=Mock())
    router.owner_arrived(21631)
    assert router.handle_message("halo", "ME LE") is True
    assert router.enabled is True
    assert router.owner_present is True

    assert router.owner_left_location("ME LE", 21631) is True

    assert router.enabled is False
    assert router.owner_present is False
    assert router.handle_message("le jawab", "other") is False


def test_non_owner_leaving_does_not_turn_ai_off():
    router = AIChatRouter(generator=Mock(return_value="hai"), send_chat=Mock())
    router.owner_arrived(21623)
    assert router.owner_left_location("random player", 32) is False
    assert router.enabled is True


def test_owner_priority_does_not_run_when_ai_is_off():
    generator = Mock(return_value="hai")
    router = AIChatRouter(generator=generator, send_chat=Mock())
    assert router.handle_message("halo", "SORANI EX") is False
    generator.assert_not_called()


def test_router_adds_aqw_class_glossary_for_abbreviation_question():
    prompts = []
    done = threading.Event()

    def generate(prompt):
        prompts.append(prompt)
        done.set()
        return "SC adalah StoneCrusher."

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.handle_message("MELE AI ON", "moderator")
    assert router.handle_message("SC itu class apa?", "player") is True
    assert done.wait(2)
    assert "StoneCrusher" in prompts[0]


def test_router_expands_abbreviations_found_in_ultra_guide_context():
    prompts = []
    done = threading.Event()

    def generate(prompt):
        prompts.append(prompt)
        done.set()
        return "SC + LR + LoO + LC."

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.handle_message("MELE AI ON", "moderator")
    assert router.handle_message("ultra darkon comp class apa?", "player") is True
    assert done.wait(2)
    assert "SC = StoneCrusher" in prompts[0]
    assert "LR = Legion Revenant" in prompts[0]
    assert "LoO = Lord of Order" in prompts[0]
    assert "LC = LightCaster" in prompts[0]


def test_agent_researches_once_then_sends_grounded_answer():
    from skua_lite.research import ResearchResult

    sent = []
    done = threading.Event()
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return "RESEARCH: where to get Blade of Awe"
        return "Blade of Awe dimulai lewat quest di Museum."

    researcher = Mock()
    researcher.answer.return_value = ResearchResult(
        question="where to get Blade of Awe",
        url="https://aqwwiki.wikidot.com/blade-of-awe",
        text="Blade of Awe is obtained from the Museum questline.",
        source="wayback",
    )
    router = AIChatRouter(
        generator=generate,
        send_chat=lambda text: (sent.append(text), done.set()),
        researcher=researcher,
    )
    router.handle_message("MELE AI ON", "moderator")

    assert router.handle_message("mele blade of awe dapet dimana?", "player") is True
    assert done.wait(2)
    researcher.answer.assert_called_once_with("where to get Blade of Awe")
    assert len(prompts) == 2
    assert "HASIL RISET (wayback)" in prompts[1]
    assert sent == ["Blade of Awe dimulai lewat quest di Museum."]


def test_agent_research_failure_does_not_leak_internal_marker():
    from skua_lite.research import ResearchResult

    sent = []
    done = threading.Event()
    calls = 0

    def generate(prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "RESEARCH: unknown AQW item"
        assert "RISET TIDAK TERSEDIA" in prompt
        return "Belum ada data yang dapat diverifikasi."

    researcher = Mock()
    researcher.answer.return_value = ResearchResult(
        question="unknown AQW item", url="", text="", source="none", error="blocked"
    )
    router = AIChatRouter(
        generator=generate,
        send_chat=lambda text: (sent.append(text), done.set()),
        researcher=researcher,
    )
    router.handle_message("MELE AI ON", "moderator")

    assert router.handle_message("mele cek unknown item", "player") is True
    assert done.wait(2)
    assert calls == 2
    assert sent == ["Belum ada data yang dapat diverifikasi."]
    assert all("RESEARCH:" not in line for line in sent)


def test_agent_does_not_research_twice_when_second_answer_requests_it_again():
    from skua_lite.research import ResearchResult

    sent = []
    done = threading.Event()
    researcher = Mock()
    researcher.answer.return_value = ResearchResult(
        question="x", url="https://aqwwiki.wikidot.com/x", text="some evidence",
        source="cache",
    )
    router = AIChatRouter(
        generator=Mock(side_effect=["RESEARCH: x", "RESEARCH: x again"]),
        send_chat=lambda text: (sent.append(text), done.set()),
        researcher=researcher,
    )
    router.handle_message("MELE AI ON", "moderator")
    assert router.handle_message("mele x?", "player") is True
    assert done.wait(2)
    researcher.answer.assert_called_once_with("x")
    assert all("RESEARCH:" not in line for line in sent)


def test_router_starts_disabled_and_only_exact_on_off_toggle():
    router = AIChatRouter(generator=Mock(return_value="hai"), send_chat=Mock())
    assert router.enabled is False
    assert router.handle_message("le apa kabar?", "user1") is False
    assert router.handle_message("MELE AI ON", "user1") is True
    assert router.enabled is True
    assert router.handle_message("mele ai on dong", "user1") is False
    assert router.handle_message("MELE AI OFF", "user1") is True
    assert router.enabled is False


def test_router_replies_to_mention_and_never_to_self_or_nonmention():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "wkwk lagi santai nih", send_chat=send)
    assert router.handle_message("MELE AI ON", "bot", is_self=True) is False
    assert router.enabled is False
    router.handle_message("MELE AI ON", "user1")
    assert router.handle_message("hai", "user2") is False
    assert router.handle_message("le lagi ngapain?", "bot", is_self=True) is False
    assert router.handle_message("le lagi ngapain?", "user2") is True
    assert done.wait(2)
    assert sent == ["wkwk lagi santai nih"]


def test_non_owner_reply_does_not_invent_tuan_title():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    # AI output that wrongly addresses a player as "Tuan".
    router = AIChatRouter(generator=lambda _message: "Tuan ada apa ya?", send_chat=send)
    router.owner_arrived(21623)
    assert done.wait(2)
    # Owner releases the lock with MODE NORMAL.
    assert router.handle_message("MODE NORMAL", "MELE", sender_id=21623) is True
    sent.clear()
    done.clear()
    assert router.handle_message("le lagi ngapain?", "stranger") is True
    assert done.wait(2)
    # The literal word "Tuan" must never reach another player.
    reply = sent[-1]
    assert "tuan" not in reply.lower(), f"non-owner reply must not contain 'Tuan': {reply!r}"


def test_mode_normal_owner_replies_use_bro_tone():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(
        generator=lambda _message: "siap bro, langsung gas", send_chat=send
    )
    router.owner_arrived(21631)
    assert done.wait(2)
    sent.clear()
    done.clear()
    # Owner releases the lock with MODE NORMAL.
    assert router.handle_message("MODE NORMAL", "ME LE", sender_id=21631) is True
    # After MODE NORMAL the owner still chats casually; reply must not be
    # addressed with "Tuan Mele" but should remain in "bro" register.
    assert router.handle_message("mel kerjain dong", "ME LE", sender_id=21631) is True
    assert done.wait(2)
    reply = sent[-1]
    assert not reply.lower().startswith("tuan mele")
    assert "bro" in reply.lower()


def test_router_truncates_reply_to_150_characters():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(generator=lambda _message: "x" * 220, send_chat=send)
    router.handle_message("MELE AI ON", "u")
    router.handle_message("mel coba jawab", "u2")
    assert done.wait(2)
    assert len(sent[0]) <= 150


def test_ai_config_reads_endpoint_key_and_model_from_environment(monkeypatch):
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "test-key")
    monkeypatch.setenv("SKUA_AI_MODEL", "test-model")
    cfg = AIConfig.from_env()
    assert cfg.base_url == "https://ai.example/v1"
    assert cfg.api_key == "test-key"
    assert cfg.model == "test-model"


def test_ai_config_loads_dotenv_file_without_overriding_process_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SKUA_AI_BASE_URL=https://file.example/v1\n"
        "SKUA_AI_API_KEY=file-key\n"
        "SKUA_AI_MODEL=file-model\n"
        "SKUA_AI_TIMEOUT=9\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("SKUA_AI_BASE_URL", raising=False)
    monkeypatch.delenv("SKUA_AI_API_KEY", raising=False)
    monkeypatch.setenv("SKUA_AI_MODEL", "process-model")
    monkeypatch.delenv("SKUA_AI_TIMEOUT", raising=False)

    cfg = AIConfig.from_env(env_file)

    assert cfg.base_url == "https://file.example/v1"
    assert cfg.api_key == "file-key"
    assert cfg.model == "process-model"
    assert cfg.timeout == 9


def test_router_remembers_recent_conversation_per_speaker():
    prompts = []
    sent = []
    done = threading.Event()

    def generate(message):
        prompts.append(message)
        return "oke"

    router = AIChatRouter(
        generator=generate,
        send_chat=lambda text: (sent.append(text), done.set()),
    )
    router.handle_message("MELE AI ON", "mod")
    assert router.handle_message("le nama gua Dio", "Dio", sender_id=501) is True
    assert done.wait(1)
    done.clear()
    assert router.handle_message("le tadi gua bilang nama gua siapa?", "Dio", sender_id=501) is True
    assert done.wait(1)
    # The second prompt must carry the earlier exchange for this speaker.
    assert "nama gua Dio" in prompts[-1]


def test_router_conversation_memory_is_per_speaker():
    prompts = []

    def generate(message):
        prompts.append(message)
        return "oke"

    router = AIChatRouter(generator=generate, send_chat=lambda _text: None)
    router.handle_message("MELE AI ON", "mod")
    router.handle_message("le rahasia gua warna merah", "Alice", sender_id=11)
    time.sleep(0.2)
    prompts.clear()
    router.handle_message("le tadi gua bilang apa?", "Bob", sender_id=22)
    time.sleep(0.2)
    assert prompts
    # Bob must not receive Alice's remembered line.
    assert "warna merah" not in prompts[-1]


def test_router_memory_survives_restart_and_reloads_from_disk(tmp_path):
    store = tmp_path / "ai_memory.json"
    prompts = []

    def generate(message):
        prompts.append(message)
        return "oke"

    first = AIChatRouter(
        generator=generate, send_chat=lambda _text: None, memory_path=store
    )
    first.handle_message("MELE AI ON", "mod")
    first.handle_message("le nomor guild gua 99", "Dio", sender_id=501)
    time.sleep(0.3)

    # Simulate process restart: a brand new router reading the same store.
    prompts.clear()
    second = AIChatRouter(
        generator=generate, send_chat=lambda _text: None, memory_path=store
    )
    second.handle_message("MELE AI ON", "mod")
    second.handle_message("le nomor guild gua berapa?", "Dio", sender_id=501)
    time.sleep(0.3)
    assert prompts
    assert "nomor guild gua 99" in prompts[-1]


def test_ai_config_reads_max_tokens_and_longer_timeout_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "k")
    monkeypatch.setenv("SKUA_AI_MODEL", "m")
    monkeypatch.delenv("SKUA_AI_TIMEOUT", raising=False)
    monkeypatch.delenv("SKUA_AI_MAX_TOKENS", raising=False)

    cfg = AIConfig.from_env(tmp_path / "missing.env")
    # Longer default thinking time and a larger completion budget than the
    # original 20s / 100 tokens.
    assert cfg.timeout >= 60
    assert cfg.max_tokens >= 400


def test_openai_generator_sends_configured_max_tokens(monkeypatch, tmp_path):
    import json
    from skua_lite import ai_router

    observed = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "hai!"}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(ai_router.urllib.request, "urlopen", fake_urlopen)
    config = AIConfig(
        base_url="https://ai.example/v1",
        api_key="secret",
        model="model-x",
        timeout=7,
        max_tokens=777,
    )
    generate = ai_router.openai_chat_generator(config)
    assert generate("halo") == "hai!"
    assert observed["payload"]["max_tokens"] == 777


def test_openai_generator_posts_chat_completion_payload(monkeypatch):
    import json
    from skua_lite.ai_router import openai_chat_generator

    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"hai!"}}]}'

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["headers"] = request.headers
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cfg = AIConfig("https://ai.example/v1", "secret", "model-x", timeout=7)
    generate = openai_chat_generator(cfg)

    assert generate("le lagi ngapain?") == "hai!"
    assert observed["url"] == "https://ai.example/v1/chat/completions"
    assert observed["payload"]["model"] == "model-x"
    assert observed["payload"]["temperature"] == 0.4
    assert observed["payload"]["messages"][1]["content"] == "le lagi ngapain?"
    assert observed["timeout"] == 7
    assert observed["headers"]["Authorization"] == "Bearer secret"


def test_router_off_during_generation_suppresses_pending_reply():
    started = threading.Event()
    release = threading.Event()
    sent = Mock()

    def generator(_message):
        started.set()
        release.wait(2)
        return "telat nih"

    router = AIChatRouter(generator=generator, send_chat=sent)
    router.handle_message("MELE AI ON", "u")
    router.handle_message("mel jawab dong", "u2")
    assert started.wait(2)
    router.handle_message("MELE AI OFF", "u")
    release.set()
    time.sleep(0.1)
    sent.assert_not_called()


def test_router_strips_wire_delimiter_and_masks_profanity():
    sent = []
    done = threading.Event()

    def send(text):
        sent.append(text)
        done.set()

    router = AIChatRouter(
        generator=lambda _message: "anjing% santai dong",
        send_chat=send,
    )
    router.handle_message("MELE AI ON", "u")
    router.handle_message("le jawab", "u2")
    assert done.wait(2)
    assert sent == ["*** santai dong"]

