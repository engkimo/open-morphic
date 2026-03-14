"""IntentAnalyzer — LLM-powered goal decomposition into subtasks.

Sprint 9.1: Complexity-aware decomposition.
  - SIMPLE tasks → 1 subtask, no LLM call (goal used directly)
  - MEDIUM/COMPLEX → LLM with complexity-appropriate guidance
"""

from __future__ import annotations

import json
import logging
import re

from domain.entities.task import SubTask
from domain.ports.llm_gateway import LLMGateway
from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer

logger = logging.getLogger(__name__)

# Stable system prompt prefix (Manus principle 1: KV-cache friendly)
_DECOMPOSE_INSTRUCTION = """\
You are a task decomposition expert. Break down the given goal into \
concrete, actionable subtasks.

Return ONLY a JSON array. Each element:
{{"description": "...", "deps": []}}

Rules:
- deps: list of 0-based indices of subtasks this depends on
- Each subtask must be action-oriented: start with a verb \
(e.g. "Write...", "Create...", "Configure...", "Test...")
- Subtask descriptions should be executable actions, not abstract concepts
- {complexity_guidance}
- No markdown, no explanation — ONLY the JSON array"""

# Keep for backward compatibility
DECOMPOSE_SYSTEM_PROMPT = _DECOMPOSE_INSTRUCTION

_COMPLEXITY_GUIDANCE = {
    TaskComplexity.MEDIUM: "Return exactly 2-3 subtasks. Keep it focused",
    TaskComplexity.COMPLEX: "Return 3-5 subtasks. Cover all major concerns",
}


class IntentAnalyzer:
    def __init__(
        self,
        llm: LLMGateway,
        kv_cache: KVCacheOptimizer | None = None,
    ) -> None:
        self._llm = llm
        self._kv_cache = kv_cache or KVCacheOptimizer()

    async def decompose(self, goal: str) -> list[SubTask]:
        """Decompose a goal into subtasks, adapting to complexity.

        SIMPLE → 1 subtask (no LLM call).
        MEDIUM/COMPLEX → LLM decomposition with guidance.
        """
        complexity = TaskComplexityClassifier.classify(goal)
        logger.info("Goal complexity: %s — %r", complexity.value, goal[:60])

        if complexity == TaskComplexity.SIMPLE:
            logger.debug("SIMPLE goal — skipping LLM, wrapping as single subtask")
            return self._create_single_subtask(goal)

        return await self._llm_decompose(goal, complexity)

    async def _llm_decompose(
        self, goal: str, complexity: TaskComplexity
    ) -> list[SubTask]:
        """Use LLM to decompose a goal with complexity-specific guidance."""
        guidance = _COMPLEXITY_GUIDANCE[complexity]
        instruction = _DECOMPOSE_INSTRUCTION.format(complexity_guidance=guidance)

        system_content = self._kv_cache.build_system_prompt(
            {"role": "decomposer", "instruction": instruction}
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": goal},
        ]
        logger.debug("LLM decomposition prompt — guidance=%r", guidance)
        response = await self._llm.complete(messages, temperature=0.3, max_tokens=1024)
        subtasks = self._parse_response(response.content)
        logger.info("LLM decomposed into %d subtask(s)", len(subtasks))
        return subtasks

    @staticmethod
    def _create_single_subtask(goal: str) -> list[SubTask]:
        """Wrap goal as a single actionable subtask (no LLM call)."""
        return [SubTask(description=goal)]

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
