"""HierarchicalSummaryManager — async manager for multi-level tree compression.

Stores hierarchy summaries in MemoryEntry.metadata (hierarchy_* keys).
No new ports needed — reuses existing MemoryRepository + optional LLMGateway.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from domain.entities.memory import MemoryEntry
from domain.ports.llm_gateway import LLMGateway
from domain.ports.memory_repository import MemoryRepository
from domain.services.hierarchical_summarizer import HierarchicalSummarizer

logger = logging.getLogger(__name__)

_HIERARCHY_SUMMARIES_KEY = "hierarchy_summaries"
_HIERARCHY_TOKEN_COUNTS_KEY = "hierarchy_token_counts"

_LLM_PROMPT = """Summarize the following text at 3 levels of compression.
Return ONLY a JSON object with keys "1", "2", "3".
- Level 1: ~40% of original length. Keep key details.
- Level 2: ~15% of original length. Main points only.
- Level 3: ~5% of original length. One-sentence topic description.

Text:
{content}"""


@dataclass(frozen=True)
class SummarizeResult:
    """Result returned from summarize()."""

    entry_id: str
    levels_built: int
    original_tokens: int
    compressed_tokens: int
    used_llm: bool


class HierarchicalSummaryManager:
    """Async manager for building and querying hierarchical summaries.

    Stores hierarchy in MemoryEntry.metadata:
      hierarchy_summaries:    JSON dict of level -> summary text
      hierarchy_token_counts: JSON dict of level -> token count

    If LLM is available, generates abstractive summaries.
    Otherwise, falls back to extractive (sentence-boundary truncation).
    """

    def __init__(
        self,
        memory_repo: MemoryRepository,
        llm_gateway: LLMGateway | None = None,
    ) -> None:
        self._memory_repo = memory_repo
        self._llm = llm_gateway

    async def summarize(self, entry_id: str) -> SummarizeResult | None:
        """Build 4-level hierarchy for a single entry.

        Returns None if entry not found.
        Skips re-summarization if hierarchy already exists.
        """
        entry = await self._memory_repo.get_by_id(entry_id)
        if entry is None:
            return None

        if self._has_hierarchy(entry):
            summaries = json.loads(entry.metadata[_HIERARCHY_SUMMARIES_KEY])
            token_counts = json.loads(entry.metadata[_HIERARCHY_TOKEN_COUNTS_KEY])
            return SummarizeResult(
                entry_id=entry_id,
                levels_built=len(summaries),
                original_tokens=token_counts.get("0", 0),
                compressed_tokens=token_counts.get(str(HierarchicalSummarizer.NUM_LEVELS - 1), 0),
                used_llm=False,
            )

        used_llm = False
        summaries: dict[int, str]

        if self._llm is not None:
            try:
                summaries = await self._summarize_with_llm(entry.content)
                used_llm = True
            except Exception:
                logger.warning(
                    "LLM summarization failed for %s, falling back to extractive",
                    entry_id,
                )
                summaries = HierarchicalSummarizer.build_extractive_hierarchy(entry.content)
        else:
            summaries = HierarchicalSummarizer.build_extractive_hierarchy(entry.content)

        token_counts = {
            level: HierarchicalSummarizer.estimate_tokens(text) for level, text in summaries.items()
        }

        # Persist hierarchy in metadata
        new_metadata = dict(entry.metadata)
        new_metadata[_HIERARCHY_SUMMARIES_KEY] = json.dumps(
            {str(k): v for k, v in summaries.items()},
            ensure_ascii=False,
        )
        new_metadata[_HIERARCHY_TOKEN_COUNTS_KEY] = json.dumps(
            {str(k): v for k, v in token_counts.items()},
        )

        updated = MemoryEntry(
            id=entry.id,
            content=entry.content,
            memory_type=entry.memory_type,
            access_count=entry.access_count,
            importance_score=entry.importance_score,
            metadata=new_metadata,
            created_at=entry.created_at,
            last_accessed=entry.last_accessed,
        )
        await self._memory_repo.delete(entry.id)
        await self._memory_repo.add(updated)

        max_level = HierarchicalSummarizer.NUM_LEVELS - 1
        return SummarizeResult(
            entry_id=entry_id,
            levels_built=len(summaries),
            original_tokens=token_counts.get(0, 0),
            compressed_tokens=token_counts.get(max_level, 0),
            used_llm=used_llm,
        )

    async def get_summary(self, entry_id: str, level: int = 0) -> str | None:
        """Retrieve summary at specific level.

        Returns None if entry not found or not summarized.
        Clamps level to valid range [0, NUM_LEVELS-1].
        """
        entry = await self._memory_repo.get_by_id(entry_id)
        if entry is None:
            return None

        if not self._has_hierarchy(entry):
            return None

        summaries = json.loads(entry.metadata[_HIERARCHY_SUMMARIES_KEY])
        clamped = max(0, min(level, HierarchicalSummarizer.NUM_LEVELS - 1))
        return summaries.get(str(clamped))

    async def retrieve_at_depth(self, query: str, max_tokens: int = 500) -> str:
        """Search memories -> select best level per entry -> assemble within budget.

        Uses MemoryRepository.search() for initial retrieval,
        then picks the deepest level that fits within remaining budget per entry.
        """
        entries = await self._memory_repo.search(query, top_k=10)
        if not entries:
            return ""

        budget = max_tokens
        parts: list[str] = []

        for entry in entries:
            if budget <= 0:
                break

            if self._has_hierarchy(entry):
                summaries = json.loads(entry.metadata[_HIERARCHY_SUMMARIES_KEY])
                token_counts_raw = json.loads(entry.metadata[_HIERARCHY_TOKEN_COUNTS_KEY])
                token_counts = {int(k): v for k, v in token_counts_raw.items()}

                level = HierarchicalSummarizer.select_level(token_counts, budget)
                text = summaries.get(str(level), entry.content)
            else:
                text = entry.content

            tokens = HierarchicalSummarizer.estimate_tokens(text)
            if tokens <= budget:
                parts.append(text)
                budget -= tokens

        return "\n---\n".join(parts)

    async def _summarize_with_llm(self, content: str) -> dict[int, str]:
        """Call LLM to generate Level 1-3 summaries. Level 0 = original."""
        assert self._llm is not None

        prompt = _LLM_PROMPT.format(content=content)
        response = await self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
        )

        parsed = json.loads(response.content)
        summaries: dict[int, str] = {0: content}
        for level in range(1, HierarchicalSummarizer.NUM_LEVELS):
            summaries[level] = parsed.get(str(level), content)
        return summaries

    @staticmethod
    def _has_hierarchy(entry: MemoryEntry) -> bool:
        """Check if entry already has hierarchy_summaries in metadata."""
        return _HIERARCHY_SUMMARIES_KEY in entry.metadata
