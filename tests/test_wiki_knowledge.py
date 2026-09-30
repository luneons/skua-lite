"""Tests for the local AQW Wiki SQLite knowledge layer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from skua_lite.wiki_knowledge import WikiKnowledge, build_wiki_database


def _source_dir(tmp_path: Path) -> Path:
    data = tmp_path / "upstream"
    data.mkdir()
    (data / "WikiItems.json").write_text(json.dumps({
        "Burning Blade": [
            "/burning-blade",
            ["Price", ["Drop", "Diabolical Warlord", "diabolical-warlord"]],
            ["Sellback", ["250", "GOLD"]],
            ["Description", "A burning blade."],
            ["Damage", [27, 33, None]],
            ["Rare", False], ["AC", False], ["Legend", False],
            ["Seasonal", False], ["Pseudo Rare", False],
            ["Special Offer", False], ["Beta", False],
            ["Color Custom", False], ["Custom Animation", False],
            "swords",
        ],
        "Void Highlord (Class)": [
            "/void-highlord-class",
            ["Price", ["Quest", "Void Highlord's Challenge", "void-highlord-s-challenge"]],
            ["Sellback", ["0", "AC"]],
            ["Description", "A class of the Nation."],
            ["Damage", "N/A"],
            ["Rare", False], ["AC", True], ["Legend", False],
            ["Seasonal", False], ["Pseudo Rare", False],
            ["Special Offer", False], ["Beta", False],
            ["Color Custom", False], ["Custom Animation", False],
            "classes",
        ],
        "ArchFiend Spear": [
            "/archfiend-spear",
            ["Price", ["Merge", "Fiend Merge", "/fiend-merge", [
                ["Fiend Token", "/fiend-token", "5"],
            ]]],
            ["Sellback", ["0", "AC"]],
            ["Description", "A spear."], ["Damage", [27, 33, None]],
            ["Rare", False], ["AC", True], ["Legend", False],
            ["Seasonal", False], ["Pseudo Rare", False],
            ["Special Offer", False], ["Beta", False],
            ["Color Custom", False], ["Custom Animation", False],
            "polearms",
        ],
    }), encoding="utf-8")
    (data / "quests.json").write_text(json.dumps({
        "Void Highlord's Challenge": {
            "name": "Void Highlord's Challenge", "slug": "/void-highlord-s-challenge",
            "location": {"name": "Tercessuinotlim", "slug": "/tercessuinotlim"},
            "npc": {"name": "Nulgath", "slug": "/nulgath-npc"},
            "rare": False, "pseudo_rare": False, "tags": ["quest"],
            "quests": [{
                "name": "Void Highlord's Challenge", "description": "Prove your worth.",
                "requirements_note": "Must be level 80.",
                "items_required": [{"name": "Roentgenium of Nulgath", "slug": "/roentgenium-of-nulgath", "qty": 15,
                                    "dropped_by": []}],
                "rewards": {"gold": 0, "exp": 0, "rep": None,
                            "items": [{"name": "Void Highlord (Class)", "slug": "/void-highlord-class", "qty": 1}]},
            }],
        },
    }), encoding="utf-8")
    (data / "merge_shops.json").write_text(json.dumps({
        "Fiend Merge": {
            "name": "Fiend Merge", "slug": "/fiend-merge",
            "npc": {"name": "Nulgath", "slug": "/nulgath-npc"},
            "location": {"name": "Tercessuinotlim", "slug": "/tercessuinotlim"},
            "rare": False, "pseudo_rare": False, "tags": ["mergeshop"],
            "tabs": [{"name": "Weapons", "items": [{
                "name": "ArchFiend Spear", "slug": "/archfiend-spear", "type_icon": "Polearm",
                "cost_type": "merge", "ingredients": [{"name": "Fiend Token", "slug": "/fiend-token", "qty": 5}],
            }]}],
        },
    }), encoding="utf-8")
    (data / "locations.json").write_text(json.dumps({
        "Underworld": {
            "name": "Underworld", "slug": "/underworld", "map_name": "underworld",
            "join_cmd": "/join underworld", "room_limit": 10, "description": "Legion realm",
            "rare": False, "pseudo_rare": False, "tags": ["location"],
            "monsters": [{"name": "Diabolical Warlord", "slug": "/diabolical-warlord", "count": 1}],
            "npcs": [], "shops": [], "quests": [],
        },
        "Tercessuinotlim": {
            "name": "Tercessuinotlim", "slug": "/tercessuinotlim", "map_name": "tercessuinotlim",
            "join_cmd": "/join tercessuinotlim", "room_limit": 6, "description": "Nation realm",
            "rare": False, "pseudo_rare": False, "tags": ["location"],
            "monsters": [], "npcs": [], "shops": [], "quests": [],
        },
    }), encoding="utf-8")
    return data


def test_builder_creates_valid_db_and_provenance(tmp_path):
    source = _source_dir(tmp_path)
    db = tmp_path / "wiki.db"

    counts = build_wiki_database(source, db, source_commit="abc123")

    assert counts["items"] == 3
    assert counts["quests"] == 1
    assert db.exists()
    with sqlite3.connect(db) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        meta = dict(con.execute("SELECT key, value FROM meta"))
    assert meta["source_commit"] == "abc123"
    assert "AQWikiTools" in meta["source_repo"]


def test_exact_drop_lookup_adds_monster_location_and_join(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    hit = wiki.lookup_item("Burning Blade")

    assert hit is not None
    assert hit.match_kind == "exact"
    assert "Diabolical Warlord" in hit.answer
    assert "/join underworld" in hit.answer
    assert len(hit.short_answer(150)) <= 150


def test_alias_lookup_resolves_vhl_and_lists_quest_requirements(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    hit = wiki.lookup_item("VHL")

    assert hit is not None
    assert hit.name == "Void Highlord (Class)"
    assert "Void Highlord's Challenge" in hit.answer
    assert "Roentgenium of Nulgath x15" in hit.answer
    assert "/join tercessuinotlim" in hit.answer


def test_merge_lookup_lists_shop_and_ingredients(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    hit = wiki.lookup_item("ArchFiend Spear")

    assert hit is not None
    assert "Fiend Merge" in hit.answer
    assert "Fiend Token x5" in hit.answer


def test_fts_and_fuzzy_find_misspelled_or_partial_item(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    assert wiki.lookup_item("burning").name == "Burning Blade"
    fuzzy = wiki.lookup_item("Burnig Blad")
    assert fuzzy is not None
    assert fuzzy.name == "Burning Blade"
    assert fuzzy.match_kind == "fuzzy"


def test_fuzzy_match_does_not_enter_router_context(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    assert wiki.context_for("Burnig Blad dimana?") == ""


def test_location_lookup_returns_join_and_observed_monsters(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    hit = wiki.lookup_location("Underworld dimana?")

    assert hit is not None
    assert hit.category == "location"
    assert "/join underworld" in hit.answer
    assert "Diabolical Warlord" in hit.answer


def test_quest_lookup_returns_npc_location_requirements_and_rewards(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    hit = wiki.lookup_quest("Void Highlord's Challenge syaratnya apa?")

    assert hit is not None
    assert hit.category == "quest"
    assert "Nulgath" in hit.answer
    assert "/join tercessuinotlim" in hit.answer
    assert "Roentgenium of Nulgath x15" in hit.answer
    assert "Void Highlord (Class) x1" in hit.answer


def test_wiki_context_routes_location_and_quest_questions(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    location = wiki.context_for("Underworld join dimana?")
    quest = wiki.context_for("Void Highlord's Challenge syaratnya apa?")

    assert "Jenis: location" in location
    assert "/join underworld" in location
    assert "Jenis: quest" in quest
    assert "Roentgenium of Nulgath x15" in quest


def test_farm_suggestion_resolves_monster_to_joinable_location(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    suggestion = wiki.suggest_farm("Diabolical Warlord")

    assert "Diabolical Warlord" in suggestion
    assert "/join underworld" in suggestion


def test_missing_database_and_unrelated_question_are_safe(tmp_path):
    wiki = WikiKnowledge(tmp_path / "missing.db")
    assert wiki.lookup_item("Burning Blade") is None
    assert wiki.context_for("halo semua apa kabar") == ""


def test_context_for_indonesian_source_question_is_grounded(tmp_path):
    db = tmp_path / "wiki.db"
    build_wiki_database(_source_dir(tmp_path), db)
    wiki = WikiKnowledge(db)

    context = wiki.context_for("Burning Blade dapat dari mana?")

    assert "KONTEKS WIKI AQW" in context
    assert "Diabolical Warlord" in context
    assert "/join underworld" in context
