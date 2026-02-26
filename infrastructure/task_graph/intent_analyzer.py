"""IntentAnalyzer — LLM-powered goal decomposition into subtasks."""

from __future__ import annotations

import json
import re

from domain.entities.task import SubTask
from domain.ports.llm_gateway import LLMGateway
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer

# Task-specific instruction appended after the stable prefix
_DECOMPOSE_INSTRUCTION = """\
You are a task decomposition expert. Break down the given goal into \
concrete, actionable subtasks.

Return ONLY a JSON array. Each element:
{"description": "...", "deps": []}

Rules:
- deps: list of 0-based indices of subtasks this depends on
- Keep subtasks atomic — one clear action each
- 2-5 subtasks for most goals
- No markdown, no explanation — ONLY the JSON array"""

# Keep for backward compatibility
DECOMPOSE_SYSTEM_PROMPT = _DECOMPOSE_INSTRUCTION


class IntentAnalyzer:
    def __init__(
        self,
        llm: LLMGateway,
        kv_cache: KVCacheOptimizer | None = None,
    ) -> None:
        self._llm = llm
        self._kv_cache = kv_cache or KVCacheOptimizer()

    async def decompose(self, goal: str) -> list[SubTask]:
        """Use LLM to decompose a goal into ordered subtasks."""
        system_content = self._kv_cache.build_system_prompt(
            {"role": "decomposer", "instruction": _DECOMPOSE_INSTRUCTION}
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": goal},
        ]
        response = await self._llm.complete(messages, temperature=0.3, max_tokens=1024)
        return self._parse_response(response.content)

    @staticmethod
    def _extract_json(content: str) -> str:
        """Extract JSON array from LLM output that may contain think tags or markdown."""
        text = content.strip()
        # Strip <think>...</think> blocks (qwen3 reasoning)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Extract from ```json ... ``` code blocks
        md_match = re.search(r"```(?:json)?\s*(\[.*?])\s*```", text, re.DOTALL)
        if md_match:
            return md_match.group(1)
        # Find first JSON array
        arr_match = re.search(r"\[.*]", text, re.DOTALL)
        if arr_match:
            return arr_match.group(0)
        return text

    @staticmethod
    def _parse_response(content: str) -> list[SubTask]:
        """Parse LLM JSON response into SubTask list with resolved deps."""
        raw_tasks = json.loads(IntentAnalyzer._extract_json(content))

        subtasks: list[SubTask] = []
        id_map: dict[int, str] = {}

        for i, raw in enumerate(raw_tasks):
            subtask = SubTask(description=raw["description"])
            id_map[i] = subtask.id
            subtasks.append(subtask)

        for i, raw in enumerate(raw_tasks):
            dep_indices = raw.get("deps", [])
            subtasks[i].dependencies = [id_map[idx] for idx in dep_indices if idx in id_map]

        return subtasks
