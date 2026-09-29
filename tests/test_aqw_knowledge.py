from skua_lite.aqw_knowledge import AQWKnowledge


def test_class_abbreviation_query_returns_full_name_and_role():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("SC itu class apa?")

    assert "SC = StoneCrusher" in context
    assert "support" in context.lower()


def test_guide_class_abbreviations_expand_into_full_names():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for(
        "cara lawan ultra darkon", guide_text="SC + LR + LoO + LC"
    )

    assert "SC = StoneCrusher" in context
    assert "LR = Legion Revenant" in context
    assert "LoO = Lord of Order" in context
    assert "LC = LightCaster" in context


def test_class_abbreviation_query_does_not_dump_enhancement_catalog():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("SC itu class apa?")

    assert "Dauntless" not in context
    assert "VHL = Void Highlord" in knowledge.context_for("VHL singkatan apa?")
    assert "AP = ArchPaladin" in knowledge.context_for("AP itu class apa?")


def test_aqw_knowledge_expands_dage_potion_shorthand():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for(
        "cara pakai potion", guide_text="UB + UM/Might + PHP"
    )

    assert "UB = Unstable Battle Elixir" in context
    assert "UM = Unstable Might Tonic" in context
    assert "PHP = Potent Honor Potion" in context


def test_enhancement_overview_lists_known_slots_only_when_requested():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("enchantment AQW ada apa aja?")

    assert "Valiance = weapon" in context
    assert "Absolution = cape" in context
    assert "Anima = helm" in context
    assert "Wizard = class" in context


def test_short_abbreviations_are_case_sensitive_to_avoid_false_hits():
    knowledge = AQWKnowledge.discover("panduan")

    # "um"/"ap" are common Indonesian fillers/words; they must not pull the
    # consumable/class tables into a normal conversation.
    assert knowledge.context_for("um nanti gua join ya") == ""
    assert knowledge.context_for("ap kabar bro") == ""
    # Uppercase shorthand still resolves.
    assert "UM = Unstable Might Tonic" in knowledge.context_for("UM itu apa?")
    assert "AP = ArchPaladin" in knowledge.context_for("AP itu class apa?")


def test_knowledge_loads_loadout_table_for_enchantment_question_about_sc():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("SC pake ench pake apa aja?")

    # Both the class and the full enhancement surface must travel, otherwise
    # the model invents a different class or claims data is missing.
    assert "SC = StoneCrusher" in context
    assert "Valiance = weapon" in context
    assert "Absolution = cape" in context
    assert "Anima = helm" in context


def test_knowledge_marks_stonecrusher_canonical_and_never_siege_captain():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("SC itu class apa?")

    assert "Siege Captain" not in context
    assert "SC = StoneCrusher" in context


def test_knowledge_returns_stonecrusher_loadout_for_sc_question():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("SC pake ench pake apa aja?")

    # The Darkon guide's Section 5 gives the concrete StoneCrusher loadout.
    assert "Valiance" in context


def test_enhancement_question_identifies_name_and_slot():
    knowledge = AQWKnowledge.discover("panduan")

    context = knowledge.context_for("Dauntless itu enhancement apa?")

    assert "Dauntless" in context
    assert "weapon" in context.lower()
