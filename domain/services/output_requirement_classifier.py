"""OutputRequirementClassifier — LLM-based classification of goal output type.

Pure domain service: depends only on LLMGateway port (no framework deps).
Determines whether a goal requires text, file, code, or data output so that
Gate ② can evaluate completion appropriately.
"""

from __future__ import annotations

import json
import logging
import re

from domain.ports.llm_gateway import LLMGateway
from domain.value_objects.output_requirement import OutputRequirement

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an output-requirement classifier. Given a user goal, determine what \
type of deliverable it requires. Return a JSON object with:
  "requirement" — one of: "text", "file", "code", "data"
  "reason"      — brief explanation (one sentence)

Definitions:
- "text": A textual answer or explanation is sufficient.
- "file": The goal explicitly or implicitly requires creating a file \
(slide, PDF, report, spreadsheet, image, presentation, etc.).
- "code": The goal requires producing a code file or script.
- "data": The goal requires fetching, analyzing, or structuring external data.

Return ONLY the JSON object.\
"""

# Map LLM response values to enum
_VALUE_MAP: dict[str, OutputRequirement] = {
    "text": OutputRequirement.TEXT,
    "file": OutputRequirement.FILE_ARTIFACT,
    "code": OutputRequirement.CODE_ARTIFACT,
    "data": OutputRequirement.DATA_ARTIFACT,
}


class OutputRequirementClassifier:
    """Classify goal output requirement via LLM analysis."""

    def __init__(self, llm: LLMGateway, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    async def classify(self, goal: str) -> OutputRequirement:
        """Return the OutputRequirement for a goal string.

        Falls back to TEXT on any error.
        """
        try:
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": goal},
            ]
            response = await self._llm.complete(
                messages,
                model=self._model,
                temperature=0.1,
                max_tokens=256,
            )
            return self._parse(response.content)
        except Exception:
            logger.warning(
                "OutputRequirementClassifier failed for goal=%r — defaulting to TEXT",
                goal[:80],
                exc_info=True,
            )
            return OutputRequirement.TEXT

    @staticmethod
    def _parse(content: str) -> OutputRequirement:
        """Extract requirement from LLM JSON response."""
        text = content.strip()
        # Strip <think> blocks (qwen3)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Extract JSON object
        obj_match = re.search(r"\{.*}", text, re.DOTALL)
        if obj_match:
            data = json.loads(obj_match.group(0))
            value = str(data.get("requirement", "text")).lower().strip()
            return _VALUE_MAP.get(value, OutputRequirement.TEXT)
        return OutputRequirement.TEXT
