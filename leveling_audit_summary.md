## Analyzed Script Logic

The installed Skua bot scripts use `CoreFarms.Experience()` to drive XP farming progression. The method (`Scripts/CoreFarms.cs`, lines 286-924) uses distinct map locations depending on the character's current level.

### Standard Progression (from `Scripts/CoreFarms.cs: Experience()`)
- **Levels 1–10:** `/oaklore`
  - Targets: Bone Berserker (`r3`, `Left`)
  - Quests: 4007, 6257
- **Levels 10–20:** `/swordhavenundead` (or `/icestormarena` if `/swordhavenundead` is bypassed via condition)
  - Targets: Undead Giant (`Gates`, `Left`)
  - Quests: 178
  - Alternatively in `/icestormarena`:
    - Levels 10-20: `r6` (Left)
- **Levels 5-10 in `/icestormarena`:** `r5` (Left)
- **Levels 20–25:** `/icestormarena`
  - Targets: `r7` (Left)
  - Quests: 6628
- **Levels 25–30:** `/icestormarena`
  - Targets: `r10` (Left)
- **Levels 30–35:** `/icestormarena`
  - Targets: `r11` (Left)
  - Quests: 6629
- **Levels 35–50:** `/icestormarena`
  - Targets: `r11` / `r14` (Left)
  - Quests: 6629
- **Levels 50–61:** `/icestormarena`
  - Targets: `r16` (Left)
- **Levels 61–75:** `/battlegrounde` (or `/icestormarena` `r17` for rank-up)
  - Targets: `/battlegrounde` `r2` (center)
  - Quests: 3991, 3992 (if not rankUpClass)
- **Levels 75–100:** `/icestormunder`
  - Targets: `r2` (Top)
  - Uses `Bot.Combat.Attack("*")`


### Alternative Army / Specialized Methods
- **Army Leveling:** `Scripts/Army/Farm/ArmyLeveling.cs`
  - Map: `/shadowbattleon` (`r11`, `Left`)
  - Quests: 9421, 9422, 9426
  - Targets level 100 via multi-client aggro farming.
- **Seven Circles War XP & Gold:** `Scripts/Farm/SevenCirclesWarXP+Gold.cs`
  - Map: `/sevencircleswar` (`r9`, `Left`)
  - Quests: 7980, 7981, 7985
- **Army Lich War Gold/XP:** `Scripts/Army/Farm/ArmyLichWarGoldXp[Mem].cs`
  - Map: `/lichwar` (`r6`, `Right`)
  - Quests: 10282, 10283
- **FireWar XP:** `Scripts/CoreFarms.cs: FireWarxp()`
  - Map: `/Firewar` (`r2`, `Right`)
  - Quests: 6294, 6295
  - Capped at Level 60.
