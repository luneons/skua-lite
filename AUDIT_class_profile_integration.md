# Audit: Class-Aware Skill Profile Integration via Local Skua AdvancedSkills

## Summary

skua-lite's combat engine (`combat.py`) uses `ClassProfile` objects to determine
skill ordering.  Today only **one hand-authored file profile exists** (`mage.json`);
all 262 other classes in the Skua `AdvancedSkills.json` catalog are unreachable
and silently fall through to `generic_profile()`, which always returns the same
`[4, 3, 2, 1]` order regardless of the actual class.

This audit maps the structural gap and recommends a portable runtime loader.

---

## 1. Current Architecture

### ClassProfile selection chain

```
profile_for(class_name)
  └─ scan class_profiles/*.json (only mage.json exists)
     └─ candidate.matches(wanted)?  → return file profile
  └─ fallback: generic_profile(class_name)
        → ClassProfile("Unknown", modes={"base": [4,3,2,1], "farm_fast": [4,3,2,1]})
```

### How the engine uses it

```python
# combat.py line 899
for ref in self.class_profile.skill_refs(self.mode):
    skill = self.state.skills.get(ref)
    ...
```

The engine iterates `skill_refs(mode)` in declared order and fires the first
skill that is unlocked, off-cooldown, and has enough mana. **Order matters**:
a class that should lead with skill 3 before skill 4 will misfire if the
generic `[4,3,2,1]` order is used.

### FarmingRuntime auto-adoption

```python
# farming.py lines 100-105
def _combat_profile(self):
    try:
        return combat.profile_for(self.profile.class_name)
    except ValueError:
        return combat.generic_profile(self.profile.class_name or "Mage")

# farming.py lines 454-466
def _adopt_equipped_profile(self, assume=""):
    ...
    profile = combat.profile_for(target)  # or generic_profile
    self.combat.set_class_profile(profile)
```

When the server reports a class change via `updateClass`, `_sync_class_profile()`
calls `_adopt_equipped_profile()`, which calls `profile_for()`. Since only
`mage.json` exists, every non-Mage class gets the generic 4-3-2-1 fallback.

---

## 2. Skua AdvancedSkills.json Structure

**Location:** `Skua.App.WPF/AdvancedSkills.json` (263 classes)

**Schema:**
```json
{
  "ClassName": {
    "ModeName": {
      "skillUseMode": "WaitForCooldown" | "UseIfAvailable",
      "skillTimeout": 100,
      "skills": [
        {"skillId": 4},
        {"skillId": 2, "rules": [{"type": "Health", "value": 70, ...}]},
        ...
      ]
    }
  }
}
```

### Key observations

| Property | Detail |
|----------|--------|
| **skillId range** | 0–5. 0=auto-attack (aa), 1–4=a1–a4, 5=i1 (item slot; only Overworld Chronomancer uses it). |
| **Mode names** | `Base` (241 classes), `Farm` (22), `Solo` (24), `Atk` (11), `Def` (14), `Supp` (3). |
| **Rules** | Health/Mana/Aura/Wait conditionals per skill entry. skua-lite currently ignores rules (engine relies on live sAct unlocked/cooldown/mana checks). |
| **Skill repetition** | Many classes repeat the same skillId in a sequence (e.g., Chrono Assassin: `[4,1,2,3,1,2,3,1,2,3,…]`). This encodes a *combo rotation*, not just priority order. |
| **Aliases** | Not present in AdvancedSkills.json (Skua matches by exact class name from `sClassName`). |

### Mode name mismatch

| skua-lite mode | Skua mode | Mapping needed |
|----------------|-----------|----------------|
| `farm_fast` | `Farm` | casefold + alias |
| `base` | `Base` | casefold |
| — | `Solo`, `Atk`, `Def`, `Supp` | expose as selectable modes |

---

## 3. Structural Gaps

### G1: Only 1 of 263 classes has a file profile
Every non-Mage class falls through to `generic_profile()`, losing the curated
skill order from Skua.

### G2: generic_profile always uses [4,3,2,1]
This is wrong for many classes. Examples:
- **Warrior** (Skua): `[1,2,3,4]` — leads with skill 1, not 4.
- **ArchPaladin** (Skua): complex rotation with conditional heal on skill 2.
- **Chaos Slayer Berserker** (Skua): `[3,1,2,4]` for Base, `[3,2,4]` for Farm.

### G3: Combo rotations are lost
skua-lite's `skill_refs()` deduplicates: the list is iterated as a priority
order, not a repeating sequence. Skua's `[4,1,2,3,1,2,3,1,2,3,…]` pattern for
Chrono classes cannot be represented as a priority set.

### G4: Mode name mismatch
`farm_fast` has no equivalent in Skua's `Farm`. The fallback in `skill_refs()`
tries the requested mode then `base`, so `Farm` mode entries are never reached.

### G5: Rules (conditionals) are ignored
The engine uses live sAct to decide readiness (unlocked, cooldown, mana), but
Skua profiles add Health %, Mana %, and Aura conditions that gate skill use.
Without these, some profiles fire defensive skills unconditionally.

### G6: No runtime loading from AdvancedSkills.json
The `profile_for()` function only reads `class_profiles/*.json` (skua-lite's
own schema). There is no code path that reads or converts the Skua JSON.

---

## 4. Recommended: Portable Runtime Loader

### Design

```python
# combat.py (new or separate module)

class AdvancedSkillsDB:
    """Load once from AdvancedSkills.json; look up by class name."""

    def __init__(self, path: Path):
        self._db: dict[str, dict[str, Any]] = json.loads(
            path.read_text(encoding="utf-8")
        )

    def profile_for(self, class_name: str, *, fallback: bool = True) -> ClassProfile:
        wanted = class_name.strip()
        # Exact match first (case-sensitive, as Skua stores it)
        entry = self._db.get(wanted)
        if entry is None:
            # Casefold search
            by_lower = {k.casefold(): (k, v) for k, v in self._db.items()}
            match = by_lower.get(wanted.casefold())
            if match:
                entry = match[1]
                wanted = match[0]
        if entry is None:
            if fallback:
                return generic_profile(class_name)
            raise KeyError(class_name)

        modes = {}
        for mode_name, mode_data in entry.items():
            # Normalize: "Base" -> "base", "Farm" -> "farm_fast"
            key = _normalize_mode_name(mode_name)
            skill_ids = [s["skillId"] for s in mode_data.get("skills", [])]
            # Deduplicate to priority order (preserving first occurrence)
            seen = set()
            ordered = []
            for sid in skill_ids:
                if sid not in seen:
                    seen.add(sid)
                    ordered.append(sid)
            modes[key] = {
                "skills": ordered,
                "fallback": "aa" if 0 not in ordered else "",
                "skill_use_mode": mode_data.get("skillUseMode", "WaitForCooldown"),
            }
        if not modes:
            return generic_profile(class_name)

        return ClassProfile(
            class_name=wanted,
            aliases=(wanted,),
            modes=modes,
        )

_MODE_ALIASES = {
    "base": "base", "farm": "farm_fast", "solo": "solo",
    "atk": "atk", "def": "def", "supp": "supp",
}

def _normalize_mode_name(name: str) -> str:
    return _MODE_ALIASES.get(name.strip().casefold(), name.strip().casefold())
```

### Integration into profile_for()

```python
_ADVANCED_DB: AdvancedSkillsDB | None = None

def profile_for(class_name: str) -> ClassProfile:
    # 1. Check hand-authored file profiles (class_profiles/*.json)
    wanted = str(class_name or "").strip().casefold()
    directory = Path(__file__).with_name("class_profiles")
    for path in sorted(directory.glob("*.json")):
        try:
            candidate = ClassProfile.load(path)
        except (OSError, ValueError):
            continue
        if candidate.matches(wanted):
            return candidate

    # 2. Check AdvancedSkills.json (lazy singleton)
    global _ADVANCED_DB
    if _ADVANCED_DB is None:
        adv_path = _find_advanced_skills_json()
        if adv_path:
            _ADVANCED_DB = AdvancedSkillsDB(adv_path)
    if _ADVANCED_DB is not None:
        try:
            return _ADVANCED_DB.profile_for(class_name, fallback=False)
        except KeyError:
            pass

    # 3. Generic fallback
    return generic_profile(class_name)

def _find_advanced_skills_json() -> Path | None:
    """Search standard locations for the Skua AdvancedSkills.json."""
    candidates = [
        Path(__file__).with_name("AdvancedSkills.json"),
        Path(os.environ.get("APPDATA", "")) / "Skua" / "AdvancedSkills.json",
        Path(os.environ.get("APPDATA", "")) / "Skua" / "UserAdvancedSkills.json",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None
```

### Deterministic fallback

When neither a hand-authored profile nor an AdvancedSkills entry exists,
`generic_profile()` should remain as-is: `[4,3,2,1]` with "aa" fallback. This
is the safest default because live `sAct` still gates every skill by cooldown,
unlock state, mana, and target kind. The ordering only determines *intent*; the
engine never fires a skill that isn't ready.

---

## 5. Recommended Tests

```python
def test_advanced_db_loads_exact_and_casefold_match():
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    p = db.profile_for("ArchPaladin")
    assert p.class_name == "ArchPaladin"
    assert p.matches("archpaladin")
    assert "base" in p.modes

def test_advanced_db_warrior_base_order_is_1234():
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    p = db.profile_for("Warrior")
    assert p.skill_refs("base") == ("a1", "a2", "a3", "a4", "aa")

def test_advanced_db_farm_mode_maps_to_farm_fast():
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    p = db.profile_for("Chaos Slayer Berserker")
    assert "farm_fast" in p.modes
    refs = p.skill_refs("farm_fast")
    assert refs[0] == "a3"  # Skua Farm: [3,2,4]

def test_advanced_db_deduplicates_chrono_combo_to_priority():
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    p = db.profile_for("Chrono Assassin")
    refs = p.skill_refs("base")
    # Chrono Assassin Base: [4,1,2,3,1,2,3,...] deduplicates to a4,a1,a2,a3
    assert refs == ("a4", "a1", "a2", "a3", "aa")

def test_advanced_db_unknown_class_raises_keyerror():
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    with pytest.raises(KeyError):
        db.profile_for("NonExistentClass", fallback=False)

def test_profile_for_prefers_hand_authored_over_advanced_db():
    # mage.json exists and should win over AdvancedSkills.json
    p = profile_for("Mage")
    assert p.skill_refs("farm_fast") == ("a4", "a2", "a1", "a3", "aa")
    # NOT ("a4", "a2", "a1", "a3", "aa") from Skua Base [4,2,1,3]

def test_profile_for_unknown_still_returns_generic():
    p = profile_for("TotallyFakeClass9999")
    assert p.matches("TotallyFakeClass9999")
    assert p.skill_refs("farm_fast") == ("a4", "a3", "a2", "a1", "aa")

def test_skill_id_zero_maps_to_aa():
    """AdvancedSkills uses skillId 0 for auto-attack (aa)."""
    db = AdvancedSkillsDB(ADVANCED_SKILLS_PATH)
    p = db.profile_for("ArchMage")
    # ArchMage Farm: [4, 0, 2] -> a4, aa, a2
    refs = p.skill_refs("farm_fast")
    assert "aa" in refs
```

---

## 6. Caveats and Future Work

| Item | Status |
|------|--------|
| **Combo sequences** (same skill repeated) | Lost on dedup. Could extend ClassProfile to support a `combo: list[str]` that the engine iterates as a round-robin cursor instead of priority scan. Not urgent: priority-scan with live sAct readiness handles most classes correctly. |
| **Rule conditionals** (Health%, Mana%, Aura) | Not implementable until skua-lite tracks auras (requires `aura+`/`aura-` packet parsing, which is already in `_CAPTURE_COMMANDS` but not in `CombatState`). Skill ordering without rules is still a large improvement over generic_profile. |
| **skillId 5 (i1 / item slot)** | Only 1 class uses it (Overworld Chronomancer). The ref mapping `5 → "i1"` is already handled by `skill_refs()`: `refs.append("aa" if index == 0 else f"a{index}")` produces `"a5"`, which isn't a valid slot. Needs a special case: `5 → "i1"`. |
| **AdvancedSkills.json bundling** | Either ship a copy in the package (`src/skua_lite/AdvancedSkills.json`) or discover it at runtime from `%APPDATA%\Skua\`. Bundling is simpler and avoids a Skua installation dependency. |
| **File size** | 151 KB (263 classes). Acceptable for one-time load. |

---

*Audit date: 2026-09-29. Investigation only — no code was modified.*
