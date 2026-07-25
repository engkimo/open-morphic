"""Execute validated chat hooks through a hook executor port."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.hook import (
    HookDefinition,
    HookDiagnostic,
    HookExecutionRequest,
    HookExecutionResult,
    HookType,
)
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.hook_executor import HookExecutorPort
from domain.ports.hook_registry import HookRegistryPort


@dataclass(frozen=True)
class ExecuteChatHookResult:
    session: ChatSession
    events: list[ChatEvent]
    diagnostics: list[HookDiagnostic]
    hook_results: list[HookExecutionResult]


class ExecuteChatHookUseCase:
    """Execute hooks already accepted by workspace validation policy."""

    def __init__(
        self,
        *,
        session_store: ChatSessionStorePort,
        hook_registry: HookRegistryPort,
        hook_executor: HookExecutorPort,
    ) -> None:
        self._session_store = session_store
        self._hook_registry = hook_registry
        self._hook_executor = hook_executor

    async def execute(
        self,
        *,
        session: ChatSession,
        hook_type: HookType,
    ) -> ExecuteChatHookResult:
        diagnostics = self._hook_registry.validate()
        failures = [diagnostic for diagnostic in diagnostics if diagnostic.status == "FAIL"]
        if failures:
            names = ", ".join(diagnostic.name for diagnostic in failures)
            raise ValueError(f"Hook diagnostics failed: {names}")

        current = session
        events: list[ChatEvent] = []
        hook_results: list[HookExecutionResult] = []

        for hook in self._hook_registry.hooks_for(hook_type):
            if not hook.enabled:
                current, skipped_event = current.record_event(
                    ChatEventType.HOOK_EXECUTION_SKIPPED,
                    self._skipped_payload_for(hook),
                )
                events.append(skipped_event)
                continue

            request = HookExecutionRequest(
                session_id=current.id,
                hook_name=hook.name,
                hook_type=hook.hook_type,
                command=hook.command,
                source_path=hook.source_path,
            )
            current, requested_event = current.record_event(
                ChatEventType.HOOK_EXECUTION_REQUESTED,
                request.model_dump(mode="json"),
            )
            events.append(requested_event)

            hook_result = await self._hook_executor.execute(request)
            hook_results.append(hook_result)
            current, completed_event = current.record_event(
                ChatEventType.HOOK_EXECUTION_COMPLETED,
                {
                    **hook_result.model_dump(mode="json"),
                    "hook_name": hook.name,
                    "hook_type": hook.hook_type.value,
                    "source_path": hook.source_path,
                },
            )
            events.append(completed_event)

        for event in events:
            await self._session_store.append_event(event)

        return ExecuteChatHookResult(
            session=current,
            events=events,
            diagnostics=diagnostics,
            hook_results=hook_results,
        )

    def _skipped_payload_for(self, hook: HookDefinition) -> dict[str, str]:
        return {
            "command": hook.command,
            "hook_name": hook.name,
            "hook_type": hook.hook_type.value,
            "reason": "disabled",
            "source_path": hook.source_path,
            "status": "skipped",
        }
