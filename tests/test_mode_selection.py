"""RED tests for startup mode selection and separated bot flows."""
from __future__ import annotations

import builtins
from unittest.mock import Mock

import pytest

from skua_lite.mode import RunMode, parse_mode, select_mode
from skua_lite import __main__ as main_mod
from skua_lite import runner


def test_parse_mode_accepts_indonesian_names_and_shortcuts():
    assert parse_mode("1") is RunMode.ASSISTANT
    assert parse_mode("ai") is RunMode.ASSISTANT
    assert parse_mode("asisten") is RunMode.ASSISTANT
    assert parse_mode("mode ai asisten") is RunMode.ASSISTANT
    assert parse_mode("2") is RunMode.FARMING
    assert parse_mode("farm") is RunMode.FARMING
    assert parse_mode("farming") is RunMode.FARMING
    assert parse_mode("mode farming") is RunMode.FARMING


def test_parse_mode_rejects_unknown_and_empty():
    assert parse_mode("") is None
    assert parse_mode("combat") is None


def test_select_mode_prompts_until_valid(monkeypatch):
    answers = iter(["ngaco", "2"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))
    printed: list[str] = []

    mode = select_mode(output=printed.append)

    assert mode is RunMode.FARMING
    assert any("tidak dikenal" in line.lower() for line in printed)


def test_select_mode_returns_explicit_without_prompt(monkeypatch):
    monkeypatch.setattr(
        builtins, "input", lambda _prompt="": pytest.fail("must not prompt")
    )
    assert select_mode(RunMode.ASSISTANT) is RunMode.ASSISTANT


def test_main_passes_cli_mode_to_runner(monkeypatch):
    observed = {}

    def fake_run(**kwargs):
        observed.update(kwargs)
        return 0

    monkeypatch.setattr(main_mod.runner, "run", fake_run)

    assert main_mod.main(["--mode", "farming", "--server", "Yorumi"]) == 0
    assert observed["mode"] is RunMode.FARMING


def test_main_without_mode_leaves_selection_to_runner(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        main_mod.runner, "run", lambda **kwargs: observed.update(kwargs) or 0
    )

    assert main_mod.main([]) == 0
    assert observed["mode"] is None


def test_orchestrator_default_target_depends_on_selected_mode(tmp_path):
    assistant = runner.Orchestrator(mode=RunMode.ASSISTANT)
    farming = runner.Orchestrator(mode=RunMode.FARMING)

    assert assistant.target_map == "yulgar-14045"
    assert farming.target_map != assistant.target_map


def test_run_prompts_for_account_flow_before_credentials(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        runner,
        "select_mode",
        lambda explicit=None: calls.append("mode") or RunMode.FARMING,
    )
    fake_accounts = object()
    monkeypatch.setattr(runner, "MultiAccountStore", lambda: fake_accounts)
    monkeypatch.setattr(
        runner,
        "prompt_farming_account_flow",
        lambda store: calls.append("account_flow") or ("single", None),
    )

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            calls.append(f"init:{kwargs['mode'].value}")
            self.bot = Mock()

        def obtain_credentials(self):
            calls.append("credentials")
            raise RuntimeError("stop after order proof")

        def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(runner, "Orchestrator", FakeOrchestrator)

    assert runner.run(mode=None) == 2
    assert calls[:4] == ["mode", "account_flow", "init:farming", "credentials"]


def test_run_routes_selected_accounts_to_multi(monkeypatch):
    selected = ["demo-one", "demo-three"]
    fake_accounts = object()
    observed = {}

    monkeypatch.setattr(runner, "select_mode", lambda explicit=None: RunMode.FARMING)
    monkeypatch.setattr(runner, "MultiAccountStore", lambda: fake_accounts)
    monkeypatch.setattr(
        runner,
        "prompt_farming_account_flow",
        lambda store: ("multi", selected),
    )

    def fake_run_multi(**kwargs):
        observed.update(kwargs)
        return 17

    monkeypatch.setattr(runner, "run_multi", fake_run_multi)

    assert runner.run(mode=RunMode.FARMING) == 17
    assert observed["accounts"] is fake_accounts
    assert observed["selected_usernames"] == selected
