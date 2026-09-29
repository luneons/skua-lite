"""Offline AQW fundamentals: class abbreviations and enhancement/potion terms.

Ultra guides are terse and rely on shorthand (SC, VHL, AP, LoO, DoT, ...). The
model can't always expand those, so this module ships a small always-available
knowledge base of class abbreviations and enhancement terminology. It also
scans the guides it already knows about so that adding "LightCaster (LC)" to a
guide injects that expansion even when the question only asks about the class.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Class abbreviations used in the Ultra guides. The "role" is intentionally a
# rough tag ("supp", "dps", "tank", "heal") the model can rephrase; it is not a
# substitute for the guide's own role descriptions.
_CLASSES = {
    "SC": ("StoneCrusher", "support"),
    "LR": ("Legion Revenant", "support"),
    "LoO": ("Lord of Order", "support"),
    "LC": ("LightCaster", "dps/heal"),
    "AP": ("ArchPaladin", "tank/support"),
    "VHL": ("Void Highlord", "dps"),
    "CAv": ("Chaos Avenger", "tank/dps"),
    "VDK": ("Verus DoomKnight", "dps"),
    "AF": ("ArchFiend", "support/dps"),
    "DoT": ("Dragon of Time", "dps"),
    "Arach": ("Arachnomancer", "support"),
    "LH": ("Legendary Hero", "support"),
    "CA": ("Chaos Avenger", "tank"),
}

# Enhancement/potion terms in the guidelines: human-readable names mapped to
# their slot (weapon, class, helm, cape, potion, etc.) for the model.
_ENHANCEMENTS = {
    "Valiance": "weapon",
    "Praxis": "weapon",
    "Elysium": "weapon",
    "Awe Blast": "weapon",
    "Arcana's Concerto": "weapon",
    "Dauntless": "weapon",
    "Absolution": "cape",
    "Penitence": "cape",
    "Vainglory": "cape",
    "Lament": "cape",
    "Avarice": "cape",
    "Anima": "helm",
    "Pneuma": "helm",
    "Forge": "helm",
    "Luck": "class enhancement",
    "Wizard": "class enhancement",
    "Healer": "class enhancement",
    "Fighter": "class enhancement",
}

_CONSUMABLES = {
    # Common shorthand used by the local guides.
    "PHP": "Potent Honor Potion",
    "UB": "Unstable Battle Elixir",
    "UM": "Unstable Might Tonic",
    "SoE": "Scroll of Enrage",
    "Scroll of Enrage": "taunt consumable",
    "Unstable Battle Elixir": "battle elixir",
    "Potent Battle Elixir": "battle elixir",
    "Unstable Might Tonic": "tonic",
    "Unstable Sage Tonic": "tonic",
    "Unstable Malevolence Elixir": "elixir",
    "Sage Tonic": "tonic",
    "Fate Tonic": "tonic",
    "Body Tonic": "tonic",
    "Might Tonic": "tonic",
    "Mana Tonic": "tonic",
    "Power Tonic": "tonic",
    "Potent Honor Potion": "potion",
    "Potent Life Potion": "potion",
    "Potent Malevolence Elixir": "elixir",
    "Potent Malevolent Elixir": "elixir",
    "Divine Elixir": "elixir",
    "Revitalize Elixir": "elixir",
    "Felicitous Philtre": "philtre",
}

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'&+]*(?: [a-zA-Z0-9'&+]+){0,2}")
_GUIDE_EXPANSION_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9&+' \\.]{2,40})\s*\(([A-Za-z0-9&+' ]{2,6})\)"
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

_LOADOUT_HINTS = (
    "enhancement", "enchantment", "ench", "enhance", "weapon", "cape", "helm",
    "gear", "build", "loadout", "equipment",
)
_CONSUMABLE_HINTS = (
    "potion", "tonic", "elixir", "consumable", "scroll", "philtre"
)


def _glossary_block(
    classes: dict[str, tuple[str, str]],
    enhancements: dict[str, str],
    consumables: dict[str, str],
) -> str:
    """Compact, fully-typed glossary block attached to the prompt."""
    lines: list[str] = []
    if classes:
        lines.append("SINGKATAN CLASS AQW (pakai ini, jangan ganti nama class):")
        for short in sorted(classes, key=lambda item: (len(item), item)):
            name, role = classes[short]
            lines.append(f"- {short} = {name} ({role})")
    if enhancements:
        lines.append("ENHANCEMENT MENURUT SLOT:")
        for term in sorted(enhancements):
            lines.append(f"- {term} = {enhancements[term]}")
    if consumables:
        lines.append("CONSUMABLE / POTION:")
        for term in sorted(consumables):
            lines.append(f"- {term} = {consumables[term]}")
    return "\n".join(lines)


@dataclass
class AQWKnowledge:
    """Scatter knowledge base of AQW class abbreviations and enhancements."""

    classes: dict[str, tuple[str, str]] = field(
        default_factory=lambda: dict(_CLASSES)
    )
    enhancements: dict[str, str] = field(
        default_factory=lambda: dict(_ENHANCEMENTS)
    )
    consumables: dict[str, str] = field(
        default_factory=lambda: dict(_CONSUMABLES)
    )
    # Guide-injected expansions found on disk, unioned at query time.
    guide_expansions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def discover(cls, base_dir: str | Path) -> "AQWKnowledge":
        knowledge = cls()
        base = Path(base_dir)
        if not base.exists():
            return knowledge
        for path in sorted(base.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            knowledge._absorb(text)
        return knowledge

    def _absorb(self, text: str) -> None:
        """Pull ``Full Name (X)`` expansions found in any guide prose."""
        prose = _FENCE_RE.sub("", text)
        for full, short in _GUIDE_EXPANSION_RE.findall(prose):
            short = short.strip()
            full = full.strip()
            if not short or not self._plausible_guide_short(short):
                continue
            # Canonical class expansions always win over guide prose.
            if short in self.classes:
                continue
            self.guide_expansions.setdefault(short, full)

    @staticmethod
    def _plausible_guide_short(short: str) -> bool:
        """Keep only abbreviation-like labels (PHP, SoE, SC, CAv), not words."""
        if not re.fullmatch(r"[A-Za-z]{2,6}", short):
            return False
        return sum(1 for ch in short if ch.isupper()) >= 2

    def context_for(self, message: str, guide_text: str = "") -> str:
        """Return the glossary paragraphs relevant to ``message`` and ``guide_text``.

        Class abbreviations and enhancement terms that appear in either the
        question or the guide context are expanded into fully-typed names so the
        model can answer even when the guide stays terse.
        """
        combined = f"{message}\n{guide_text}"
        found_classes: dict[str, tuple[str, str]] = {}
        for short, (name, role) in self._all_classes().items():
            if _has_abbreviation(combined, short) or _contains_token(
                combined, name
            ):
                found_classes[short] = (name, role)

        enhancements = self._all_enhancements()
        found_enh = {
            term: slot for term, slot in enhancements.items()
            if _contains_token(combined, term)
        }
        if any(_contains_token(combined, hint) for hint in _LOADOUT_HINTS):
            found_enh = enhancements

        consumables = self._all_consumables()
        found_consumables = {
            term: kind for term, kind in consumables.items()
            if (
                _has_abbreviation(combined, term)
                if _plausible_short(term)
                else _contains_token(combined, term)
            )
        }
        if any(_contains_token(combined, hint) for hint in _CONSUMABLE_HINTS):
            found_consumables = consumables

        return _glossary_block(found_classes, found_enh, found_consumables)

    def _all_classes(self) -> dict[str, tuple[str, str]]:
        merged = dict(self.classes)
        for short, full in self.guide_expansions.items():
            merged.setdefault(short, (full, "class/term"))
        return merged

    def _all_enhancements(self) -> dict[str, str]:
        return dict(self.enhancements)

    def _all_consumables(self) -> dict[str, str]:
        return dict(self.consumables)

    def loadout_block(self) -> str:
        """The full enhancement/consumable surface, for loadout questions."""
        return _glossary_block(
            {}, dict(self._all_enhancements()), dict(self._all_consumables())
        )

    def expand_class_names(self, message: str) -> list[str]:
        """Return full class names whose short forms occur in ``message``."""
        return [
            name for short, (name, _role) in self._all_classes().items()
            if _has_abbreviation(message or "", short)
        ]


def _has_abbreviation(text: str, token: str) -> bool:
    """Case-sensitive short-form match to avoid AP/UM false positives."""
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text
    ) is not None


def _contains_token(text: str, token: str) -> bool:
    """Case-insensitive whole-word match (handles multi-word names too)."""
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        text,
        re.IGNORECASE,
    ) is not None


def _plausible_short(short: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]{2,6}", short)) and sum(
        char.isupper() for char in short
    ) >= 2