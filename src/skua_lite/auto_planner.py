"""Autonomous goal loop (Observe → Decide → Act), decoupled from menus.

The planner owns one explicit `.auto <tujuan>` session at a time. It reads
server-pushed state (area snapshots, combat engine, inventory tracker) and
emits the next action through the injected farming/combat runtime. Agentic
means: the bot decides the next step from observations — not the user typing
one command per step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import threading
import time
from typing import Any, Callable


@dataclass(slots=True)
class AutoGoal:
    """One autonomous objective the planner is working on."""

    kind: str  # "drop" | "quest" | "class" | "farm"
    target_name: str = ""
    drop_name: str = ""
    quantity: int = 1
    map_name: str = ""
    started_at: float = 0.0


_ITEM_QUANTITY_RE = re.compile(r"\bx\s*(\d+)\b|(\d+)\s*(?:buah|x)\b", re.IGNORECASE)
_QUEST_ID_RE = re.compile(r"\b(?:quest)\s+(\d+)\b", re.IGNORECASE)
_DROP_SPLIT_RE = re.compile(r"\bdari\b", re.IGNORECASE)


class AutoGoalParser:
    """Turn one owner sentence into an :class:`AutoGoal` (or None).

    Only a closed set of goal shapes counts as an autonomous objective; any
    other `.auto ...` sentence is refused instead of guessed, so the bot never
    wanders off from a vague instruction.
    """

    @classmethod
    def parse(cls, text: str) -> AutoGoal | None:
        raw = " ".join(str(text or "").split())
        if not raw:
            return None
        clean = raw.casefold()
        if clean.startswith(".auto"):
            clean = clean[len(".auto"):].strip()
            raw = raw[len(".auto"):].strip()
        elif clean.startswith("auto "):
            clean = clean[len("auto "):].strip()
            raw = raw[len("auto "):].strip()
        else:
            return None
        if not raw:
            return None

        if "quest" in clean:
            return cls._quest(raw)
        if clean.startswith(("cari ", "farming ", "farm ", "lawan ")):
            return cls._hunt(raw)
        return None

    @classmethod
    def _quest(cls, raw: str) -> AutoGoal | None:
        match = _QUEST_ID_RE.search(raw)
        if not match:
            return None
        return AutoGoal(kind="quest", target_name=match.group(1))

    @classmethod
    def _hunt(cls, raw: str) -> AutoGoal | None:
        body = re.sub(
            r"^(cari|farming|farm|lawan)\s+", "", raw, flags=re.IGNORECASE
        ).strip()
        if not body:
            return None
        quantity = 1
        qty_match = _ITEM_QUANTITY_RE.search(body)
        if qty_match:
            quantity = max(1, int(qty_match.group(1) or qty_match.group(2)))
            body = body[: qty_match.start()].strip() + " " + body[qty_match.end():].strip()
        drop_name = body
        target_name = ""
        parts = _DROP_SPLIT_RE.split(body, maxsplit=1)
        if len(parts) == 2:
            drop_name, target_name = parts[0].strip(), parts[1].strip()
        drop_name = drop_name.strip(" ,.")
        target_name = target_name.strip(" ,.")
        if not drop_name:
            return None
        if target_name:
            return AutoGoal(
                kind="drop", target_name=target_name,
                drop_name=drop_name, quantity=quantity,
            )
        return AutoGoal(kind="farm", target_name=drop_name, quantity=quantity)


@dataclass(slots=True, frozen=True)
class AutoDecision:
    """One action the loop wants performed next. Pure data, no side effects.

    ``reason`` is diagnostic metadata: two decisions are the same decision when
    they ask for the same action, so it is excluded from equality.
    """

    action: str  # idle | paused | attack | move | wait | turn_in | done
    cell: str = ""
    reason: str = field(default="", compare=False)
    quest_id: int = 0


@dataclass(slots=True)
class AutoObservation:
    """Everything the planner is allowed to look at when deciding."""

    connected: bool = True
    enemies_in_cell: int = 0
    cells_with_enemies: tuple[str, ...] = ()
    drop_count: int = 0
    quest_ready: bool = False


class AutoPlanner:
    """Own the `.auto <tujuan>` loop for one bot session.

    The loop is deliberately a pure decision core plus three injected seams
    (``observe``, ``count_drop``, ``apply``): the planner decides *what* should
    happen next from observed state, while the bot layer performs the packet
    I/O. That keeps every branch testable without a network.
    """

    def __init__(
        self,
        bot: Any,
        *,
        on_log: Callable[[str], None] | None = None,
        clock: Callable[[], float] | None = None,
        count_drop: Callable[[AutoGoal], int] | None = None,
        observe: Callable[[], AutoObservation] | None = None,
        apply: Callable[[AutoDecision], None] | None = None,
    ) -> None:
        self.bot = bot
        self._on_log = on_log or (lambda _message: None)
        self._clock = clock or time.time
        self._count_drop = count_drop or (lambda _goal: 0)
        self._observe = observe or AutoObservation
        self._apply = apply or (lambda _decision: None)
        self._lock = threading.RLock()
        self._goal: AutoGoal | None = None
        self._active = False
        self._last_decision = AutoDecision("idle")

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def current_goal(self) -> AutoGoal | None:
        with self._lock:
            return self._goal

    @property
    def last_decision(self) -> AutoDecision:
        with self._lock:
            return self._last_decision

    def decide(self, observation: AutoObservation) -> AutoDecision:
        """Observe → decide. Never emits packets; the caller applies it."""
        with self._lock:
            goal = self._goal
            active = self._active
        if goal is None or not active:
            return self._remember(AutoDecision("idle"))
        if not observation.connected:
            # A dropped socket invalidates the goal: never fire packets into a
            # dead connection, and never declare success from stale state.
            return self._remember(AutoDecision("paused", reason="koneksi putus"))

        if goal.kind == "drop":
            count = self._int(self._count_drop, goal)
            if goal.quantity > 0 and count >= goal.quantity:
                decision = AutoDecision(
                    "done",
                    reason=f"{goal.drop_name} x{goal.quantity} terkumpul",
                )
                self._finish()
                return self._remember(decision)
        elif goal.kind == "quest" and observation.quest_ready:
            decision = AutoDecision(
                "turn_in", reason="quest siap diserahkan",
                quest_id=self._safe_int(goal.target_name),
            )
            self._finish()
            return self._remember(decision)

        if observation.enemies_in_cell > 0:
            return self._remember(AutoDecision("attack", reason=goal.target_name))
        if observation.cells_with_enemies:
            return self._remember(
                AutoDecision("move", cell=observation.cells_with_enemies[0])
            )
        return self._remember(AutoDecision("wait", reason="menunggu respawn"))

    def tick(self) -> bool:
        """Run one loop iteration. False = the loop no longer owns the bot."""
        if not self.active:
            return False
        decision = self.decide(self._safe_observe())
        self._apply(decision or AutoDecision("idle"))
        return True

    def _safe_observe(self) -> AutoObservation:
        try:
            observed = self._observe()
        except Exception as exc:  # a broken observer must not kill the loop
            self._on_log(f"[AUTO] gagal observasi: {exc}")
            return AutoObservation(connected=False)
        if isinstance(observed, AutoObservation):
            return observed
        return AutoObservation()

    def _remember(self, decision: AutoDecision) -> AutoDecision:
        with self._lock:
            self._last_decision = decision
        return decision

    def _finish(self) -> None:
        with self._lock:
            self._active = False

    @staticmethod
    def _int(counter: Callable[[AutoGoal], int], goal: AutoGoal) -> int:
        try:
            return int(counter(goal))
        except Exception:
            return 0

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    def set_goal(self, goal: AutoGoal) -> AutoGoal:
        """Start pursuing one goal; replaces any previous goal."""
        goal.started_at = self._clock()
        with self._lock:
            self._goal = goal
            self._active = True
            self._last_decision = AutoDecision("idle")
        self._on_log(f"[AUTO] tujuan baru: {self.status()}")
        return goal

    def stop(self) -> None:
        """Stop the current goal (owner `Berhenti` or disconnect)."""
        with self._lock:
            self._goal = None
            self._active = False
            self._last_decision = AutoDecision("idle")
        self._on_log("[AUTO] tujuan dihentikan")

    def status(self) -> str:
        """Human-readable one-liner for the owner; never touches network."""
        with self._lock:
            goal = self._goal
            if goal is None or not self._active:
                return "tidak ada tujuan auto aktif"
            if goal.kind == "drop":
                return (
                    f"Mencari {goal.drop_name} x{goal.quantity} "
                    f"dari {goal.target_name or 'musuh map ini'}"
                )
            if goal.kind == "quest":
                return f"Menyelesaikan quest {goal.target_name}"
            return f"Tujuan {goal.kind}: {goal.target_name}"
