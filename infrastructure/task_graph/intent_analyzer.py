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
from domain.services.discussion_role_extractor import DiscussionRoleExtractor
from domain.services.model_capability_registry import ModelCapabilityRegistry
from domain.services.model_preference_extractor import ModelPreferenceExtractor
from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.collaboration_mode import CollaborationMode
from domain.value_objects.model_preference import ModelPreference
from domain.value_objects.task_complexity import TaskComplexity
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer

logger = logging.getLogger(__name__)

# Stable system prompt prefix (Manus principle 1: KV-cache friendly)
_DECOMPOSE_INSTRUCTION = """\
You are a task decomposition expert. Break down the given goal into \
concrete, actionable subtasks.

Return ONLY a JSON array. Each element:
{{"description": "...", "produces": ["artifact_name"], "consumes": ["artifact_name"], "deps": []}}

Rules:
- deps: list of 0-based indices of subtasks this depends on
- produces: names of artifacts this subtask will output (e.g. "search_results", "code", "analysis")
- consumes: names of artifacts from previous subtasks this step needs as input
- Each subtask must be action-oriented: start with a verb \
(e.g. "Write...", "Create...", "Configure...", "Test...")
- Subtask descriptions should be executable actions, not abstract concepts
- {complexity_guidance}
- No markdown, no explanation — ONLY the JSON array"""

# Keep for backward compatibility
DECOMPOSE_SYSTEM_PROMPT = _DECOMPOSE_INSTRUCTION

_COMPLEXITY_GUIDANCE = {
    TaskComplexity.MEDIUM: (
        "Return exactly 2-3 subtasks. Keep it focused.\n"
        "- If subtasks are INDEPENDENT, set deps=[] on both so they run in parallel.\n"
        "- Only add deps when one subtask truly needs the output of another"
    ),
    TaskComplexity.COMPLEX: (
        "Return 3-5 subtasks. Cover all major concerns.\n"
        "- Maximize parallelism: independent subtasks MUST have deps=[].\n"
        "- Add a final synthesis subtask that depends on the parallel results.\n"
        "- Example structure: [search A (deps=[]), search B (deps=[]), synthesize (deps=[0,1])]"
    ),
}

# --- Multi-model decomposition (Sprint 12.6) ---

_MULTI_MODEL_INSTRUCTION = """\
You are a task decomposition expert. The user wants multiple AI models to \
collaborate on a task. Assign differentiated subtasks to each model based on \
its strengths.

Available models and their strengths:
{model_capabilities}

Collaboration mode: {collaboration_mode}

User goal: {goal}

Return ONLY a JSON array. Each element:
{{"description": "...", "model": "<model_id>", {role_field}\
"produces": ["artifact_name"], "consumes": ["artifact_name"], "deps": []}}

Rules:
- "model" MUST be one of: {model_ids}
- deps: list of 0-based indices of subtasks this depends on
- produces: names of artifacts this subtask will output (e.g. "search_results", "code", "analysis")
- consumes: names of artifacts from previous subtasks this step needs as input
- Each subtask must be action-oriented: start with a verb
- Assign subtasks that leverage each model's specific strengths
- {mode_guidance}
{role_instruction}\
- No markdown, no explanation — ONLY the JSON array"""

_MODE_GUIDANCE: dict[CollaborationMode, str] = {
    CollaborationMode.PARALLEL: (
        "All models work on the same domain from different angles. "
        "Include a final synthesis subtask."
    ),
    CollaborationMode.COMPARISON: (
        "Each model tackles the same task independently. Include a final comparison subtask."
    ),
    CollaborationMode.DIVERSE: (
        "Each model handles a different aspect. "
        "No synthesis needed unless aspects need integration."
    ),
    CollaborationMode.AUTO: ("Decide the best strategy. Include synthesis if it adds value."),
}


class IntentAnalyzer:
    def __init__(
        self,
        llm: LLMGateway,
        kv_cache: KVCacheOptimizer | None = None,
        role_assignment: bool = True,
    ) -> None:
        self._llm = llm
        self._kv_cache = kv_cache or KVCacheOptimizer()
        self._role_assignment = role_assignment

    async def decompose(self, goal: str) -> list[SubTask]:
        """Decompose a goal into subtasks, adapting to complexity.

        Multi-model → per-model subtasks (no LLM call, parallel).
        Single-model → normal decomposition + preferred_model stamp.
        No model → existing behaviour (SIMPLE=1 subtask, MEDIUM/COMPLEX=LLM).
        """
        preference = ModelPreferenceExtractor.extract(goal)

        if preference.is_multi_model:
            logger.info(
                "Multi-model goal detected — %d models (%s): %s",
                len(preference.models),
                preference.collaboration_mode.value,
                preference.models,
            )
            try:
                subtasks = await self._llm_multi_model_decompose(preference)
                # LLM must produce at least as many subtasks as models
                if len(subtasks) < len(preference.models):
                    logger.warning(
                        "LLM returned %d subtask(s) for %d models — static fallback",
                        len(subtasks),
                        len(preference.models),
                    )
                    subtasks = self._create_per_model_subtasks(preference)
            except Exception:
                logger.warning("LLM multi-model decomposition failed — static fallback")
                subtasks = self._create_per_model_subtasks(preference)

            # Sprint 13.3: Assign discussion roles to subtasks.
            # User-specified roles take priority; LLM generates if enabled.
            self._assign_roles(goal, subtasks)

            # Multi-model is at least MEDIUM complexity
            complexity = max(
                TaskComplexityClassifier.classify(preference.clean_goal),
                TaskComplexity.MEDIUM,
            )
            for st in subtasks:
                st.complexity = complexity
            return subtasks

        # Determine working goal: use clean_goal if model was found
        working_goal = preference.clean_goal if preference.has_preferences else goal
        complexity = TaskComplexityClassifier.classify(working_goal)

        # TD-158: Tool-requiring tasks (weather, search, news) need at least
        # MEDIUM complexity for multi-step decomposition (parallel search + synthesis).
        if (
            complexity == TaskComplexity.SIMPLE
            and TaskComplexityClassifier.requires_tools(working_goal)
        ):
            complexity = TaskComplexity.MEDIUM
            logger.info(
                "Goal upgraded SIMPLE→MEDIUM (requires tools) — %r", goal[:60],
            )

        logger.info("Goal complexity: %s — %r", complexity.value, goal[:60])

        if complexity == TaskComplexity.SIMPLE:
            logger.debug("SIMPLE goal — skipping LLM, wrapping as single subtask")
            subtasks = self._create_single_subtask(goal)
        else:
            subtasks = await self._llm_decompose(working_goal, complexity)

        # Stamp complexity + preferred_model on all subtasks
        for st in subtasks:
            st.complexity = complexity
            if preference.has_preferences:
                st.preferred_model = preference.models[0]
        return subtasks

    async def _llm_decompose(self, goal: str, complexity: TaskComplexity) -> list[SubTask]:
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

        # TD-159: Quality gate — if any subtask description is too short,
        # the local LLM produced unusable results (e.g. single-word "取得").
        # Fall back to template decomposition with proper descriptions.
        min_desc_len = 8
        if any(len(st.description.strip()) < min_desc_len for st in subtasks):
            logger.warning(
                "LLM decomposition quality too low (descriptions < %d chars) — "
                "falling back to template decomposition",
                min_desc_len,
            )
            subtasks = self._template_decompose(goal, complexity)

        return subtasks

    async def _llm_multi_model_decompose(self, preference: ModelPreference) -> list[SubTask]:
        """Use LLM to decompose a multi-model goal into differentiated subtasks."""
        capabilities_text = ModelCapabilityRegistry.format_for_prompt(preference.models)

        # Sprint 13.3: When role_assignment is enabled, ask LLM to also generate roles
        if self._role_assignment:
            role_field = '"role": "<discussion role>", '
            role_instruction = (
                "- Assign a unique, task-relevant discussion role to each participant\n"
            )
        else:
            role_field = ""
            role_instruction = ""

        instruction = _MULTI_MODEL_INSTRUCTION.format(
            model_capabilities=capabilities_text,
            collaboration_mode=preference.collaboration_mode.value,
            goal=preference.clean_goal,
            model_ids=", ".join(preference.models),
            mode_guidance=_MODE_GUIDANCE[preference.collaboration_mode],
            role_field=role_field,
            role_instruction=role_instruction,
        )
        messages = [
            {"role": "system", "content": instruction},
            {"role": "user", "content": preference.clean_goal},
        ]
        logger.debug(
            "LLM multi-model decomposition — mode=%s, models=%s",
            preference.collaboration_mode.value,
            preference.models,
        )
        response = await self._llm.complete(messages, temperature=0.3, max_tokens=1024)
        subtasks = self._parse_multi_model_response(response.content, preference.models)
        logger.info("LLM multi-model decomposed into %d subtask(s)", len(subtasks))
        return subtasks

    def _assign_roles(self, goal: str, subtasks: list[SubTask]) -> None:
        """Assign roles to subtasks from user input or LLM-generated JSON.

        Sprint 13.3: Roles are free-form strings — no hardcoded types.
        User-specified roles (via regex extraction) take priority.
        If not found and role_assignment is enabled, subtasks may already
        have roles from LLM decomposition (parsed from JSON "role" field).
        """
        user_roles = DiscussionRoleExtractor.extract(goal)
        if user_roles:
            for i, st in enumerate(subtasks):
                st.role = user_roles[i % len(user_roles)]
            logger.info("User-specified roles assigned: %s", user_roles)
            return

        # Check if LLM decomposition already assigned roles
        has_llm_roles = any(st.role for st in subtasks)
        if has_llm_roles:
            logger.info(
                "LLM-generated roles: %s",
                [st.role for st in subtasks if st.role],
            )

    @staticmethod
    def _parse_multi_model_response(content: str, allowed_models: tuple[str, ...]) -> list[SubTask]:
        """Parse LLM JSON response for multi-model decomposition."""
        raw_tasks = json.loads(IntentAnalyzer._extract_json(content))

        subtasks: list[SubTask] = []
        id_map: dict[int, str] = {}
        produces_map: dict[int, list[str]] = {}
        consumes_map: dict[int, list[str]] = {}

        for i, raw in enumerate(raw_tasks):
            model = raw.get("model", "")
            if model not in allowed_models:
                model = allowed_models[i % len(allowed_models)]
            subtask = SubTask(
                description=raw["description"],
                preferred_model=model,
                role=raw.get("role"),
            )
            id_map[i] = subtask.id
            produces_map[i] = raw.get("produces", [])
            consumes_map[i] = raw.get("consumes", [])
            subtasks.append(subtask)

        for i, raw in enumerate(raw_tasks):
            dep_indices = raw.get("deps", [])
            subtasks[i].dependencies = [id_map[idx] for idx in dep_indices if idx in id_map]

        # Sprint 13.4a / TD-159: Apply artifact flow from LLM.
        IntentAnalyzer._apply_artifact_flow(
            subtasks, produces_map, consumes_map, llm_decomposed=True,
        )

        return subtasks

    @staticmethod
    def _template_decompose(goal: str, complexity: TaskComplexity) -> list[SubTask]:
        """Template-based decomposition when LLM produces low-quality results.

        TD-159: Local LLMs (Ollama) sometimes produce single-word subtask
        descriptions ("取得", "解析", "表示") that are unusable.  This method
        provides well-structured subtasks with parallel branches.
        """
        if complexity == TaskComplexity.MEDIUM:
            subtasks = [
                SubTask(description=f"Search and gather information: {goal}"),
                SubTask(description=f"Analyze findings and compose answer: {goal}"),
            ]
            # Parallel: both independent, synthesis depends on both
            # Actually for 2-step, make second depend on first
            subtasks[1].dependencies = [subtasks[0].id]
        else:
            # COMPLEX: parallel search + synthesis
            subtasks = [
                SubTask(description=f"Research primary information: {goal}"),
                SubTask(description=f"Gather supporting data and context: {goal}"),
                SubTask(description=(
                    f"Synthesize all findings into a comprehensive answer: {goal}"
                )),
            ]
            # First two are parallel, synthesis depends on both
            subtasks[2].dependencies = [subtasks[0].id, subtasks[1].id]

        logger.info(
            "Template decomposition — %d subtasks, parallel=%s",
            len(subtasks),
            any(not st.dependencies for st in subtasks),
        )
        return subtasks

    @staticmethod
    def _create_single_subtask(goal: str) -> list[SubTask]:
        """Wrap goal as a single actionable subtask (no LLM call)."""
        return [SubTask(description=goal)]

    @staticmethod
    def _create_per_model_subtasks(preference: ModelPreference) -> list[SubTask]:
        """Create one subtask per model with inferred artifact chain.

        TD-096: Static fallback now applies artifact flow inference so that
        later subtasks receive output from earlier ones.  This ensures
        artifact chaining works even when LLM decomposition fails.
        """
        subtasks = [
            SubTask(
                description=f"[{model}] {preference.clean_goal}",
                preferred_model=model,
            )
            for model in preference.models
        ]
        # Infer linear artifact chain and dependencies
        IntentAnalyzer._apply_artifact_flow(subtasks, {}, {})
        return subtasks

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
        produces_map: dict[int, list[str]] = {}
        consumes_map: dict[int, list[str]] = {}

        for i, raw in enumerate(raw_tasks):
            subtask = SubTask(description=raw["description"])
            id_map[i] = subtask.id
            produces_map[i] = raw.get("produces", [])
            consumes_map[i] = raw.get("consumes", [])
            subtasks.append(subtask)

        for i, raw in enumerate(raw_tasks):
            dep_indices = raw.get("deps", [])
            subtasks[i].dependencies = [id_map[idx] for idx in dep_indices if idx in id_map]

        # Sprint 13.4a / TD-159: Apply artifact flow from LLM.
        # llm_decomposed=True preserves LLM's parallel structure (deps=[]).
        IntentAnalyzer._apply_artifact_flow(
            subtasks, produces_map, consumes_map, llm_decomposed=True,
        )

        return subtasks

    @staticmethod
    def _apply_artifact_flow(
        subtasks: list[SubTask],
        produces_map: dict[int, list[str]],
        consumes_map: dict[int, list[str]],
        *,
        llm_decomposed: bool = False,
    ) -> None:
        """Apply artifact flow: use LLM-specified or infer linear chain.

        Sprint 13.4a: If LLM provided produces/consumes, use them directly.
        Otherwise, infer a linear artifact chain — each subtask produces an
        artifact named 'step_N_output' that the next subtask consumes.

        TD-096: Also infer dependencies from artifact flow via
        ArtifactDependencyResolver (TD-097 shared domain service).

        TD-159: When ``llm_decomposed=True``, the subtasks already have deps
        set from LLM output (including explicit ``deps=[]`` for parallel).
        In this case, do NOT infer linear chain — respect LLM's parallelism.
        """
        from domain.services.artifact_dependency_resolver import ArtifactDependencyResolver

        has_any = any(produces_map.get(i) or consumes_map.get(i) for i in range(len(subtasks)))

        if has_any:
            # Use LLM-specified artifact flow
            for i, st in enumerate(subtasks):
                produces = produces_map.get(i, [])
                consumes = consumes_map.get(i, [])
                if produces:
                    st.output_artifacts = {name: "" for name in produces}
                if consumes:
                    st.input_artifacts = {name: "" for name in consumes}
            # Resolve deps from artifact flow (additive to LLM deps)
            ArtifactDependencyResolver.resolve(subtasks)
        elif len(subtasks) > 1 and not llm_decomposed:
            # Static/fallback path only: infer linear chain when LLM wasn't used.
            # When LLM decomposed (llm_decomposed=True), deps are already set
            # from LLM output — don't override parallel structure with linear chain.
            for i, st in enumerate(subtasks):
                artifact_name = f"step_{i}_output"
                st.output_artifacts = {artifact_name: ""}
                if i > 0:
                    prev_name = f"step_{i - 1}_output"
                    st.input_artifacts = {prev_name: ""}
            ArtifactDependencyResolver.resolve(subtasks)
