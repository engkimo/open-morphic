"""TwoEngineDebate — LiteLLM-backed CouncilDebatePort with LLM-judge resolver.

Spec: `specs/council-pilot/spec.md` (FR-1..FR-6, FR-11, NFR-1, NFR-8).
Plan: `specs/council-pilot/plan.md` §Infrastructure impls.

Two LLM calls per candidate (one Argument each) + one resolver call (Decision).
System prompts are module-level constants so the KV cache stays warm across
repeat debates (NFR-8). Per-debate values move to the user message.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.ports.council_debate import CouncilDebatePort
from domain.ports.llm_gateway import LLMGateway
from domain.value_objects.agent_engine import AgentEngineType

logger = logging.getLogger(__name__)


_ARGUMENT_SYSTEM_PROMPT = (
    "You are an autonomous agent CLI engine arguing why you are the best choice "
    "for a given subtask. Respond with a single JSON object and nothing else, "
    "matching this schema exactly:\n"
    "{\n"
    '  "capability_claim": str,  // why your capabilities fit this subtask\n'
    '  "cost_claim": str,        // expected cost relative to alternatives\n'
    '  "risk_claim": str,        // failure modes you are likely to avoid\n'
    '  "recommended_approach": str  // a concrete approach you would take\n'
    "}\n"
    "Each field must be a non-empty string. Do not wrap the JSON in code fences."
)


_RESOLVER_SYSTEM_PROMPT = (
    "You are an impartial judge resolving a debate between two autonomous agent "
    "engines competing for a subtask. You will receive two Argument JSON objects "
    "and the subtask description. Pick the engine whose argument is more credible "
    "for this specific subtask. Reference both engines by name in your rationale. "
    "Respond with a single JSON object and nothing else, matching this schema "
    "exactly:\n"
    "{\n"
    '  "agent_engine": str,  // must equal one of the two engine names provided\n'
    '  "rationale": str      // why you picked that engine over the other\n'
    "}\n"
    "Do not wrap the JSON in code fences."
)


class TwoEngineDebate(CouncilDebatePort):
    def __init__(
        self,
        llm_gateway: LLMGateway,
        resolver_model: str = "gemini/gemini-2.5-flash",
        per_call_timeout_seconds: float = 8.0,
    ) -> None:
        self._llm_gateway = llm_gateway
        self._resolver_model = resolver_model
        self._per_call_timeout_seconds = per_call_timeout_seconds

    async def debate(
        self,
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> tuple[Decision, list[Argument]]:
        if len(candidates) != 2:
            raise ValueError(
                f"two-engine debate requires exactly 2 candidates, got {len(candidates)}"
            )

        arguments: list[Argument] = []
        for engine in candidates:
            arguments.append(await self._generate_argument(engine, subtask))

        decision = await self._resolve(arguments, subtask, candidates)
        return decision, arguments

    async def _generate_argument(
        self,
        engine: AgentEngineType,
        subtask: SubtaskBrief,
    ) -> Argument:
        user_message = (
            f"Engine name: {engine.value}\n"
            f"Subtask id: {subtask.id}\n"
            f"Subtask task_type: {subtask.task_type.value}\n"
            f"Subtask description:\n{subtask.description}\n"
        )
        response = await self._llm_gateway.complete(
            messages=[
                {"role": "system", "content": _ARGUMENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.4,
        )
        payload = _parse_json(response.content)
        if payload is None:
            raise ValueError(f"malformed_argument: {engine.value}")
        try:
            return Argument(
                engine=engine,
                capability_claim=str(payload["capability_claim"]),
                cost_claim=str(payload["cost_claim"]),
                risk_claim=str(payload["risk_claim"]),
                recommended_approach=str(payload["recommended_approach"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"malformed_argument: {engine.value}") from exc

    async def _resolve(
        self,
        arguments: list[Argument],
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> Decision:
        # Randomize the order arguments are presented to the judge to mitigate
        # positional bias (plan §Risks row 3).
        order = list(range(len(arguments)))
        random.shuffle(order)
        body = "\n\n".join(
            f"Argument from {arguments[i].engine.value}:\n"
            f"{json.dumps(_argument_to_dict(arguments[i]), ensure_ascii=False)}"
            for i in order
        )
        user_message = (
            f"Subtask id: {subtask.id}\n"
            f"Subtask task_type: {subtask.task_type.value}\n"
            f"Subtask description:\n{subtask.description}\n\n"
            f"Candidate engines: {[c.value for c in candidates]}\n\n"
            f"{body}"
        )
        response = await self._llm_gateway.complete(
            messages=[
                {"role": "system", "content": _RESOLVER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model=self._resolver_model,
            temperature=0.2,
        )
        payload = _parse_json(response.content)
        if payload is None:
            raise ValueError("resolver_error: malformed JSON")
        try:
            chosen_name = str(payload["agent_engine"])
            rationale = str(payload["rationale"])
        except (KeyError, TypeError) as exc:
            raise ValueError("resolver_error: missing fields") from exc

        chosen = _match_engine(chosen_name, candidates)
        if chosen is None:
            raise ValueError(
                f"resolver_error: engine '{chosen_name}' not in candidates"
            )

        return Decision(
            description=f"Council picked {chosen.value} for subtask {subtask.id}",
            agent_engine=chosen,
            rationale=rationale,
        )


def _parse_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _argument_to_dict(arg: Argument) -> dict[str, str]:
    return arg.model_dump(exclude={"engine"})


def _match_engine(
    name: str,
    candidates: list[AgentEngineType],
) -> AgentEngineType | None:
    needle = name.strip().lower()
    for c in candidates:
        if c.value.lower() == needle:
            return c
    for c in candidates:
        if c.value.lower() in needle or needle in c.value.lower():
            return c
    return None
