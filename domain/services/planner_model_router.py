"""PlannerModelRouter — domain service selecting a planner model per goal.

The router consults a ``GoalClassifierPort`` and applies AD-2 (confidence
gating) + AD-3 (reason-category normalization) + safe-by-default fallback
on classifier failure/timeout. It is pure (no I/O of its own beyond the
injected port + bus) and side-effect-light: a single best-effort event is
published per call (publish failures are swallowed, see AD-5 + plan.md
Risks table — privacy + resilience).

Spec: `specs/goal-classifier-router/spec.md`.
Plan: `specs/goal-classifier-router/plan.md` AD-2/AD-3/AD-5.
"""

from __future__ import annotations

import asyncio
import hashlib

from domain.ports.event_bus import EventBusPort
from domain.ports.goal_classifier import GoalClassifierPort
from domain.value_objects.council_events import GoalClassified, ReasonCategory
from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel

_NON_ASCII_KEYWORDS = (
    "japanese",
    "non-ascii",
    "non ascii",
    "cjk",
    "kanji",
    "katakana",
    "hiragana",
)
_QUOTED_KEYWORDS = (
    "quoted",
    "quote",
    "filename",
    "file name",
    "column",
    "table name",
)
_MULTILINGUAL_KEYWORDS = (
    "multilingual",
    "proper noun",
    "proper-noun",
    "named entity",
)


def _hash16(goal: str) -> str:
    return hashlib.sha256(goal.encode("utf-8")).hexdigest()[:16]


def _categorize_sonnet_reason(reason: str) -> ReasonCategory:
    """Map a classifier ``reason`` string to a Prometheus label bucket.

    Closed keyword map per AD-3 — lives in the router (not the classifier
    prompt) so prompt drift does not explode label cardinality.
    """
    lowered = reason.lower()
    if any(k in lowered for k in _NON_ASCII_KEYWORDS):
        return "non_ascii_entity"
    if any(k in lowered for k in _QUOTED_KEYWORDS):
        return "quoted_specific_entity"
    if any(k in lowered for k in _MULTILINGUAL_KEYWORDS):
        return "multilingual_or_proper_noun"
    return "multilingual_or_proper_noun"


class PlannerModelRouter:
    """Select a planner model for a single goal."""

    def __init__(
        self,
        *,
        classifier: GoalClassifierPort,
        event_bus: EventBusPort,
        enabled: bool,
        haiku_confidence_threshold: float = 0.7,
        classifier_timeout_ms: int = 1500,
        default_model: PlannerModel = PlannerModel.SONNET,
    ) -> None:
        self._classifier = classifier
        self._event_bus = event_bus
        self._enabled = enabled
        self._threshold = haiku_confidence_threshold
        self._timeout_s = classifier_timeout_ms / 1000.0
        self._default_model = default_model

    async def select_for(
        self, goal: str
    ) -> tuple[PlannerModel, GoalClassification | None]:
        if not self._enabled:
            return self._default_model, None

        try:
            verdict = await asyncio.wait_for(
                self._classifier.classify(goal), timeout=self._timeout_s
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:  # noqa: UP041
            return await self._fallback_sonnet(
                goal, reason=f"classifier_failed: timeout ({exc.__class__.__name__})"
            )
        except Exception as exc:  # noqa: BLE001 — safe-by-default policy
            return await self._fallback_sonnet(
                goal, reason=f"classifier_failed: {exc}"
            )

        if verdict.model is PlannerModel.HAIKU and verdict.confidence >= self._threshold:
            await self._emit(
                goal,
                chosen=PlannerModel.HAIKU,
                category="generic_tech_english",
                classification=verdict,
            )
            return PlannerModel.HAIKU, verdict

        if verdict.model is PlannerModel.HAIKU:
            fallback = self._cloned(
                verdict,
                model=PlannerModel.SONNET,
                reason=f"low_confidence: {verdict.reason}",
            )
            await self._emit(
                goal,
                chosen=PlannerModel.SONNET,
                category="low_confidence",
                classification=fallback,
            )
            return PlannerModel.SONNET, fallback

        category = _categorize_sonnet_reason(verdict.reason)
        await self._emit(
            goal,
            chosen=PlannerModel.SONNET,
            category=category,
            classification=verdict,
        )
        return PlannerModel.SONNET, verdict

    async def _fallback_sonnet(
        self, goal: str, *, reason: str
    ) -> tuple[PlannerModel, GoalClassification]:
        fallback = GoalClassification(
            model=PlannerModel.SONNET,
            reason=reason[:200],
            confidence=0.0,
            latency_ms=0,
            cost_usd=0.0,
        )
        await self._emit(
            goal,
            chosen=PlannerModel.SONNET,
            category="classifier_failed",
            classification=fallback,
        )
        return PlannerModel.SONNET, fallback

    @staticmethod
    def _cloned(
        verdict: GoalClassification,
        *,
        model: PlannerModel,
        reason: str,
    ) -> GoalClassification:
        return GoalClassification(
            model=model,
            reason=reason[:200],
            confidence=verdict.confidence,
            latency_ms=verdict.latency_ms,
            cost_usd=verdict.cost_usd,
        )

    async def _emit(
        self,
        goal: str,
        *,
        chosen: PlannerModel,
        category: ReasonCategory,
        classification: GoalClassification,
    ) -> None:
        event = GoalClassified(
            goal_hash=_hash16(goal),
            chosen_model=chosen,
            confidence=classification.confidence,
            reason_category=category,
            classifier_latency_ms=classification.latency_ms,
            classifier_cost_usd=classification.cost_usd,
        )
        try:
            await self._event_bus.publish(event)
        except Exception:  # noqa: BLE001 — event emission is best-effort
            return
