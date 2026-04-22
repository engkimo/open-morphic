"""ArtifactDependencyResolver — infer subtask dependencies from artifact flow.

TD-097: When subtasks are recreated (e.g. during plan approval), their IDs
change and any previously-inferred dependency references become stale.
This resolver re-infers dependencies from output_artifacts/input_artifacts
(producer→consumer relationships) so they always reference correct IDs.

If no artifacts exist, infers a linear chain (subtask[i] depends on [i-1]).
Pure domain service — no external dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.entities.task import SubTask

logger = logging.getLogger(__name__)


class ArtifactDependencyResolver:
    """Infer dependencies between subtasks from their artifact flow."""

    @staticmethod
    def resolve(subtasks: list[SubTask]) -> None:
        """Infer dependencies from artifact flow on existing subtasks.

        Two paths:
        1. If any subtask has output_artifacts or input_artifacts, build a
           producer→consumer map and add dependencies accordingly.
        2. If no artifacts exist and there are 2+ subtasks, infer a linear
           chain: subtask[i] depends on subtask[i-1].

        Idempotent — existing dependencies are preserved, duplicates avoided.
        """
        if len(subtasks) <= 1:
            return

        has_artifacts = any(st.output_artifacts or st.input_artifacts for st in subtasks)

        if has_artifacts:
            ArtifactDependencyResolver._resolve_from_artifacts(subtasks)
        else:
            ArtifactDependencyResolver._resolve_linear_chain(subtasks)

    @staticmethod
    def _resolve_from_artifacts(subtasks: list[SubTask]) -> None:
        """Infer deps from producer→consumer artifact relationships."""
        producer_index: dict[str, int] = {}
        for i, st in enumerate(subtasks):
            if st.output_artifacts:
                for name in st.output_artifacts:
                    producer_index[name] = i

        for i, st in enumerate(subtasks):
            if st.input_artifacts:
                for name in st.input_artifacts:
                    producer_idx = producer_index.get(name)
                    if producer_idx is not None and producer_idx != i:
                        dep_id = subtasks[producer_idx].id
                        if dep_id not in st.dependencies:
                            st.dependencies.append(dep_id)
                            logger.debug(
                                "Artifact dep: subtask[%d] depends on subtask[%d] via '%s'",
                                i,
                                producer_idx,
                                name,
                            )

    @staticmethod
    def _resolve_linear_chain(subtasks: list[SubTask]) -> None:
        """Infer linear chain: subtask[i] depends on subtask[i-1]."""
        for i in range(1, len(subtasks)):
            prev_id = subtasks[i - 1].id
            if prev_id not in subtasks[i].dependencies:
                subtasks[i].dependencies.append(prev_id)
