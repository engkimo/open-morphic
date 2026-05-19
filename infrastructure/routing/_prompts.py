"""Shared classifier prompt + parser for goal-classifier adapters.

Both ``LLMGoalClassifier`` (remote Anthropic Haiku) and ``LocalGoalClassifier``
(Ollama qwen3:8b) use the same SYSTEM_PROMPT — this keeps the contract
byte-identical, which (a) lets us A/B-compare adapters fairly and (b) keeps
LiteLLM's prompt-cache hit window stable for the remote path (NFR-5 / TD-190).

The parser tolerates two common qwen3 habits:
- ``<think>...</think>`` reasoning blocks before the JSON
- triple-backtick ``json`` fenced output

Anything that cannot be coerced to a valid ``GoalClassification`` raises
``ClassificationParseError`` — callers map it to the Sonnet fallback path.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from domain.value_objects.goal_classification import GoalClassification
from domain.value_objects.planner_model import PlannerModel

SYSTEM_PROMPT = """\
You are a 2-class goal router for a planning LLM. Decide which planner model \
should handle the user goal. Return ONLY a JSON object with these keys:
  "model"      (string) — exactly "haiku" or "sonnet".
  "confidence" (number) — 0.0 to 1.0.
  "reason"     (string) — <=200 chars, English, no PII.

Choose "haiku" only if ALL of the following hold:
  - goal is generic-tech / English
  - no Japanese / CJK / non-ASCII characters
  - no quoted specific entities (file names, column names, place names)
  - no proper nouns referring to a specific real-world entity

Otherwise choose "sonnet" (the safe default for entity-preservation).

A "quoted specific entity" is ANY token in single or double quotes that names \
a concrete field, file, column, table, identifier, or proper noun. Even \
generic-sounding names like 'date', "user", or 'id.csv' count as quoted \
specific entities when wrapped in quotes — the quoting itself signals the \
caller wants that exact token preserved verbatim. Route those to "sonnet".

Examples (verdict only — DO NOT echo these in your answer):
  "Build a REST API in Python"
    -> {"model":"haiku","confidence":0.95,"reason":"generic tech, no entities"}
  "Sort a CSV file by the 'date' column"
    -> {"model":"sonnet","confidence":0.9,"reason":"quoted column entity 'date'"}
  "東京から京都への新幹線の最安ルートを調査"
    -> {"model":"sonnet","confidence":0.95,"reason":"non-ASCII place names"}

Return JSON only. No prose outside the JSON object."""


class ClassificationParseError(ValueError):
    """Raised when the classifier output cannot be coerced to a valid verdict."""


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_FIRST_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _extract_json_blob(raw: str) -> str:
    if not raw or not raw.strip():
        raise ClassificationParseError("empty classifier output")

    cleaned = _THINK_BLOCK_RE.sub("", raw).strip()

    fence_match = _JSON_FENCE_RE.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    obj_match = _FIRST_OBJECT_RE.search(cleaned)
    if not obj_match:
        raise ClassificationParseError(
            "no JSON object found in classifier output"
        )
    return obj_match.group(0)


def parse_classification(
    raw: str, *, latency_ms: int, cost_usd: float
) -> GoalClassification:
    """Parse a raw classifier response to a ``GoalClassification``."""
    blob = _extract_json_blob(raw)

    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ClassificationParseError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ClassificationParseError(
            f"expected JSON object, got {type(data).__name__}"
        )

    model_raw = data.get("model")
    try:
        model = PlannerModel(model_raw)
    except ValueError as exc:
        raise ClassificationParseError(
            f"invalid model value: {model_raw!r}"
        ) from exc

    if "reason" not in data or "confidence" not in data:
        raise ClassificationParseError(
            "classifier output missing required field (reason / confidence)"
        )

    reason = str(data["reason"])[:200].strip() or "n/a"

    try:
        return GoalClassification(
            model=model,
            reason=reason,
            confidence=float(data["confidence"]),
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise ClassificationParseError(
            f"validation failed: {exc}"
        ) from exc
