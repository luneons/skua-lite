"""Portable per-class combat rotations derived from Skua AdvancedSkills.

Only skill order is imported. Rule predicates are intentionally not executed:
skua-lite still gates every action against the live ``sAct`` payload for unlock,
cooldown, mana, and target kind.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MODE_MAP = {"Base": "base", "Farm": "farm_fast"}
_FALLBACK_MODE_ORDER = ("Solo", "Atk", "Def", "Supp", "Dodge")
_VALID_SKILL_IDS = {0, 1, 2, 3, 4, 5}


def _skill_order(block: Any) -> list[int]:
    if not isinstance(block, dict):
        return []
    result: list[int] = []
    seen: set[int] = set()
    skills = block.get("skills")
    if not isinstance(skills, list):
        return []
    for raw in skills:
        if not isinstance(raw, dict):
            continue
        try:
            skill_id = int(raw.get("skillId"))
        except (TypeError, ValueError):
            continue
        if skill_id not in _VALID_SKILL_IDS or skill_id in seen:
            continue
        seen.add(skill_id)
        result.append(skill_id)
    return result


def rotations_from_advanced_skills(raw: Any) -> dict[str, dict[str, list[int]]]:
    """Convert Skua's database to compact class -> local-mode -> skill order."""
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, list[int]]] = {}
    for raw_name, raw_modes in raw.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_modes, dict):
            continue
        modes: dict[str, list[int]] = {}
        for source_mode, local_mode in _MODE_MAP.items():
            order = _skill_order(raw_modes.get(source_mode))
            if order:
                modes[local_mode] = order
        # Some Skua entries intentionally have no Base. In that case use the
        # first authored specialist mode rather than a fabricated generic order.
        if "base" not in modes:
            for source_mode in _FALLBACK_MODE_ORDER:
                order = _skill_order(raw_modes.get(source_mode))
                if order:
                    modes["base"] = order
                    break
        if "farm_fast" not in modes and "base" in modes:
            modes["farm_fast"] = list(modes["base"])
        if modes:
            result[name] = modes
    return result


def _bundled_path() -> Path:
    return Path(__file__).with_name("data") / "class_rotations.json"


def load_rotations(path: str | os.PathLike[str] | None = None) -> dict[str, dict[str, list[int]]]:
    """Load an explicit live Skua file, else the bundled portable snapshot."""
    candidate = Path(path) if path is not None else None
    if candidate is not None and candidate.is_file():
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            converted = rotations_from_advanced_skills(raw)
            if converted:
                return converted
        except (OSError, ValueError, TypeError):
            pass
    try:
        bundled = json.loads(_bundled_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return bundled if isinstance(bundled, dict) else {}


def lookup_rotations(
    class_name: str,
    *,
    path: str | os.PathLike[str] | None = None,
) -> dict[str, list[int]] | None:
    wanted = str(class_name or "").strip().casefold()
    if not wanted:
        return None
    for name, modes in load_rotations(path).items():
        if name.casefold() == wanted:
            return {key: list(value) for key, value in modes.items()}
    return None
