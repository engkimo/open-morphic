"""IntentAnalyzer — LLM-powered goal decomposition into subtasks."""

from __future__ import annotations

import json

from domain.entities.task import SubTask
from domain.ports.llm_gateway import LLMGateway

DECOMPOSE_SYSTEM_PROMPT = """\
You are a task decomposition expert. Break down the given goal into \
concrete, actionable subtasks.

Return ONLY a JSON array. Each element:
{"description": "...", "deps": []}

Rules:
- deps: list of 0-based indices of subtasks this depends on
- Keep subtasks atomic — one clear action each
- 2-5 subtasks for most goals
- No markdown, no explanation — ONLY the JSON array"""


class IntentAnalyzer:
    def __init__(self, llm: LLMGateway) -> None:
        self._llm = llm

    async def decompose(self, goal: str) -> list[SubTask]:
        """Use LLM to decompose a goal into ordered subtasks."""
        messages = [
            {"role": "system", "content": DECOMPOSE_SYSTEM_PROMPT},
            {"role": "user", "content": goal},
        ]
        response = await self._llm.complete(
            messages, temperature=0.3, max_tokens=1024
        )
        return self._parse_response(response.content)

    @staticmethod
    def _parse_response(content: str) -> list[SubTask]:
        """Parse LLM JSON response into SubTask list with resolved deps."""
        raw_tasks = json.loads(content.strip())

        subtasks: list[SubTask] = []
        id_map: dict[int, str] = {}

        for i, raw in enumerate(raw_tasks):
            subtask = SubTask(description=raw["description"])
            id_map[i] = subtask.id
            subtasks.append(subtask)

        for i, raw in enumerate(raw_tasks):
            dep_indices = raw.get("deps", [])
            subtasks[i].dependencies = [
                id_map[idx] for idx in dep_indices if idx in id_map
            ]

        return subtasks
