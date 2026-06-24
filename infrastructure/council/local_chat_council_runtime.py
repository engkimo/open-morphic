"""Local deterministic council runtime for the Morphic Chat CLI MVP."""

from __future__ import annotations

from domain.entities.chat_session import ChatSession
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import ContextIndex
from domain.ports.council_runtime import CouncilRuntimePort


class LocalChatCouncilRuntime(CouncilRuntimePort):
    """Cheap deterministic council used before external engine adapters are wired."""

    async def deliberate(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        context_note = f"{len(context.sources)} context sources indexed"
        planner = CouncilTurn(
            role=CouncilRole.PLANNER,
            engine_id="local",
            content=f"Plan next step for: {user_message}",
            evidence=[context_note, f"permission={session.permission_mode.value}"],
        )
        critic = CouncilTurn(
            role=CouncilRole.CRITIC,
            engine_id="local",
            content="Keep the change scoped and verify with unit tests.",
            evidence=["Clean Architecture boundary must hold"],
        )
        leader = CouncilTurn(
            role=CouncilRole.LEADER,
            engine_id="local",
            content="Proceed with the planner proposal after bounded verification.",
            evidence=planner.evidence + critic.evidence,
        )
        decision = CouncilDecision(
            leader_engine_id=leader.engine_id,
            selected_role=planner.role,
            selected_content=planner.content,
            rationale="Local MVP runtime favors the smallest verifiable next step.",
            evidence=leader.evidence,
        )
        return [planner, critic, leader], decision
