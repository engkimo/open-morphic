"""Plan chat hook execution without running hook commands."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities.chat_event import ChatEvent, ChatEventType
from domain.entities.chat_session import ChatSession
from domain.entities.hook import HookDefinition, HookDiagnostic, HookType
from domain.ports.chat_session_store import ChatSessionStorePort
from domain.ports.hook_registry import HookRegistryPort


@dataclass(frozen=True)
class PlanChatHooksResult:
    session: ChatSession
    events: list[ChatEvent]
    diagnostics: list[HookDiagnostic]


class PlanChatHooksUseCase:
    """Record hook execution plans while keeping command execution deferred."""

    def __init__(
        self,
        *,
        session_store: ChatSessionStorePort,
        hook_registry: HookRegistryPort,
    ) -> None:
        self._session_store = session_store
        self._hook_registry = hook_registry

    async def execute(
        self,
        *,
        session: ChatSession,
        hook_type: HookType,
    ) -> PlanChatHooksResult:
        diagnostics = self._hook_registry.validate()
        failures = [diagnostic for diagnostic in diagnostics if diagnostic.status == "FAIL"]
        if failures:
            names = ", ".join(diagnostic.name for diagnostic in failures)
            raise ValueError(f"Hook diagnostics failed: {names}")

        current = session
        events: list[ChatEvent] = []
        for hook in self._hook_registry.hooks_for(hook_type):
            event_type = (
                ChatEventType.HOOK_EXECUTION_PLANNED
                if hook.enabled
                else ChatEventType.HOOK_EXECUTION_SKIPPED
            )
            current, event = current.record_event(
                event_type,
                self._payload_for(hook),
            )
            events.append(event)

        for event in events:
            await self._session_store.append_event(event)

        return PlanChatHooksResult(
            session=current,
            events=events,
            diagnostics=diagnostics,
        )

    def _payload_for(self, hook: HookDefinition) -> dict[str, str]:
        payload = {
            "command": hook.command,
            "hook_name": hook.name,
            "hook_type": hook.hook_type.value,
            "source_path": hook.source_path,
        }
        if hook.enabled:
            return {**payload, "status": "planned"}
        return {**payload, "reason": "disabled", "status": "skipped"}
