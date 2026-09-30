from skua_lite.reasoning_engine import FailureKind, diagnose_failure


def test_turn_in_missing_quest_progress_is_item_progress():
    reason = diagnose_failure("ccqr", "Missing Quest Progress", quest_id=7979)
    assert reason.kind == FailureKind.ITEMS_MISSING
    assert reason.quest_id == 7979
    assert any(word in reason.diagnosis.casefold() for word in ("item", "syarat", "farming"))


def test_turn_in_quest_progress_variation_is_item_progress():
    reason = diagnose_failure(
        "ccqr", "Quest progress is not completed yet.", quest_id=7980
    )
    assert reason.kind == FailureKind.ITEMS_MISSING
    assert reason.quest_id == 7980
