"""Per-class skill rotations derived from Skua's AdvancedSkills.json.

The bot must fire the skills of the class it is actually wearing, not a Mage
rotation for everything. Skua ships the real per-class orders; this module
converts that file into the compact shape skua-lite already understands and
falls back to the bundled snapshot when the Skua install is absent.
"""
import json

import pytest

from skua_lite import class_rotations, combat


def _raw(**classes):
    return classes


def test_rotation_order_is_preserved_from_skua_lists():
    raw = {"Warrior": {"Base": {"skills": [{"skillId": 1}, {"skillId": 2}, {"skillId": 4}]}}}
    rotations = class_rotations.rotations_from_advanced_skills(raw)
    assert rotations["Warrior"]["base"] == [1, 2, 4]


def test_repeated_skill_entries_are_deduplicated_keeping_first_use():
    raw = {"X": {"Farm": {"skills": [
        {"skillId": 4}, {"skillId": 3}, {"skillId": 4}, {"skillId": 1}, {"skillId": 3},
    ]}}}
    rotations = class_rotations.rotations_from_advanced_skills(raw)
    assert rotations["X"]["farm_fast"] == [4, 3, 1]


def test_basic_attack_zero_is_kept_in_place():
    raw = {"ArchMage": {"Farm": {"skills": [{"skillId": 4}, {"skillId": 0}, {"skillId": 2}]}}}
    rotations = class_rotations.rotations_from_advanced_skills(raw)
    assert rotations["ArchMage"]["farm_fast"] == [4, 0, 2]


def test_skua_modes_map_to_local_modes_and_unknown_modes_are_ignored():
    raw = {"Y": {
        "Base": {"skills": [{"skillId": 1}]},
        "Farm": {"skills": [{"skillId": 2}]},
        "Solo": {"skills": [{"skillId": 3}]},
    }}
    rotations = class_rotations.rotations_from_advanced_skills(raw)
    assert set(rotations["Y"]) == {"base", "farm_fast"}
    assert rotations["Y"]["base"] == [1]
    assert rotations["Y"]["farm_fast"] == [2]


def test_classes_without_usable_skills_are_dropped():
    raw = {
        "Empty": {"Base": {"skills": []}},
        "Junk": {"Base": {"skills": [{"skillId": 9}]}},
        "Good": {"Base": {"skills": [{"skillId": 1}]}},
    }
    rotations = class_rotations.rotations_from_advanced_skills(raw)
    assert set(rotations) == {"Good"}


def test_malformed_entries_do_not_crash_the_converter():
    raw = {"Z": {"Base": "bukan dict"}}
    assert class_rotations.rotations_from_advanced_skills(raw) == {}


def test_bundled_snapshot_covers_real_classes_with_real_orders():
    rotations = class_rotations.load_rotations()
    assert len(rotations) > 100
    # Skua's Warrior Base order starts on skill 1, not the generic 4.
    assert rotations["Warrior"]["base"] == [1, 2, 3, 4]


def test_explicit_skua_file_overrides_the_bundled_snapshot(tmp_path):
    source = tmp_path / "AdvancedSkills.json"
    source.write_text(json.dumps({
        "Warrior": {"Base": {"skills": [{"skillId": 3}, {"skillId": 1}]}},
    }), encoding="utf-8")

    rotations = class_rotations.load_rotations(path=source)

    assert rotations["Warrior"]["base"] == [3, 1]


def test_missing_override_file_falls_back_to_bundled_snapshot(tmp_path):
    rotations = class_rotations.load_rotations(path=tmp_path / "nope.json")
    assert rotations["Warrior"]["base"] == [1, 2, 3, 4]


def test_lookup_is_case_insensitive_and_reports_unknown_classes():
    assert class_rotations.lookup_rotations("warrior")["base"] == [1, 2, 3, 4]
    assert class_rotations.lookup_rotations("Tidak Ada Class Ini") is None


def test_profile_for_uses_the_class_rotation_not_the_generic_order():
    profile = combat.profile_for("Warrior")
    assert profile.matches("Warrior")
    # Generic would be a4, a3, a2, a1: Warrior must lead with its own skill 1.
    assert profile.skill_refs("farm_fast") == ("a1", "a2", "a3", "a4", "aa")


def test_profile_for_keeps_archmage_farm_order_with_staff_hit_third():
    profile = combat.profile_for("ArchMage")
    assert profile.skill_refs("farm_fast") == ("a4", "aa", "a2")


def test_hand_verified_file_profile_still_wins_over_rotations():
    profile = combat.profile_for("Mage")
    assert profile.skill_refs("farm_fast") == ("a4", "a2", "a1", "a3", "aa")


def test_unknown_class_still_falls_back_to_generic_order():
    profile = combat.profile_for("Class Yang Tidak Ada")
    assert profile.skill_refs("farm_fast") == ("a4", "a3", "a2", "a1", "aa")


def test_skill_five_maps_to_the_item_ref_used_by_the_engine():
    profile = combat.ClassProfile.from_dict({
        "class_name": "Overworld Chronomancer",
        "aliases": ["Overworld Chronomancer"],
        "modes": {"base": {"skills": [5, 2], "fallback": "aa"}},
    })
    assert profile.skill_refs("base") == ("i1", "a2", "aa")


def test_generic_profile_still_refuses_nothing_for_unknown_names():
    profile = combat.generic_profile("")
    assert profile.class_name == "Unknown"
