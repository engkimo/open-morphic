"""OpenHandsDriver — runs tasks via OpenHands REST API."""

from __future__ import annotations

import asyncio
import time

import httpx

from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.services.engine_cost_calculator import EngineCostCalculator
from domain.value_objects.agent_engine import AgentEngineType


class OpenHandsDriver(AgentEnginePort):
    """Agent engine backed by OpenHands REST API.

    Creates a conversation via POST, then polls for completion.
    Supports optional Bearer token auth.
    """

    engine_type: AgentEngineType = AgentEngineType.OPENHANDS

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        model: str = "claude-sonnet-4-6",
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 10.0,
        **kwargs: object,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=self._headers(),
        ) as client:
            func = getattr(client, method)
            return await func(path, **kwargs)

    async def _ensure_settings(self, model: str) -> bool:
        """Submit LLM settings to OpenHands if needed (required before conversations)."""
        try:
            resp = await self._request(
                "post",
                "/api/settings",
                json={
                    "llm_model": model,
                    "llm_api_key": self._api_key,
                    "agent": "CodeActAgent",
                },
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def run_task(
        self,
        task: str,
        model: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> AgentEngineResult:
        resolved_model = model or self._model
        start = time.monotonic()

        # Ensure LLM settings are configured
        if self._api_key:
            await self._ensure_settings(resolved_model)

        # Create conversation — try new API first, fall back to legacy
        try:
            create_resp = await self._request(
                "post",
                "/api/conversations",
                json={"initial_user_msg": task},
                timeout=30.0,
            )
            # Fallback to legacy endpoint if new one fails
            if create_resp.status_code in (404, 405):
                create_resp = await self._request(
                    "post",
                    "/api/v1/app-conversations",
                    json={"task": task, "model": resolved_model},
                    timeout=30.0,
                )
            if create_resp.status_code not in (200, 201):
                return AgentEngineResult(
                    engine=AgentEngineType.OPENHANDS,
                    success=False,
                    output="",
                    error=f"Create conversation failed: {create_resp.status_code}",
                    duration_seconds=time.monotonic() - start,
                )
            create_data = create_resp.json()
            conversation_id = create_data.get("conversation_id", "")
        except Exception as exc:
            return AgentEngineResult(
                engine=AgentEngineType.OPENHANDS,
                success=False,
                output="",
                error=f"Create request failed: {exc}",
                duration_seconds=time.monotonic() - start,
            )

        # Poll for completion
        poll_interval = 2.0
        deadline = start + timeout_seconds
        try:
            while time.monotonic() < deadline:
                poll_resp = await self._request(
                    "get",
                    f"/api/conversations/{conversation_id}",
                    timeout=10.0,
                )
                if poll_resp.status_code != 200:
                    return AgentEngineResult(
                        engine=AgentEngineType.OPENHANDS,
                        success=False,
                        output="",
                        error=f"Poll failed: {poll_resp.status_code}",
                        duration_seconds=time.monotonic() - start,
                        metadata={"conversation_id": conversation_id},
                    )

                poll_data = poll_resp.json()
                status = poll_data.get("status", "").lower()

                if status in ("completed", "idle", "stopped"):
                    oh_metadata: dict = {"conversation_id": conversation_id}
                    oh_usage = poll_data.get("usage") or poll_data.get("token_usage")
                    if oh_usage:
                        oh_metadata["usage"] = oh_usage
                    cost_usd = EngineCostCalculator.calculate(resolved_model, oh_usage)
                    return AgentEngineResult(
                        engine=AgentEngineType.OPENHANDS,
                        success=status != "stopped",
                        output=poll_data.get("result", ""),
                        cost_usd=cost_usd,
                        duration_seconds=time.monotonic() - start,
                        model_used=resolved_model,
                        metadata=oh_metadata,
                    )

                if status in ("error",):
                    return AgentEngineResult(
                        engine=AgentEngineType.OPENHANDS,
                        success=False,
                        output="",
                        error=poll_data.get("error", f"Status: {status}"),
                        duration_seconds=time.monotonic() - start,
                        metadata={"conversation_id": conversation_id},
                    )

                await asyncio.sleep(poll_interval)

            # Timeout
            return AgentEngineResult(
                engine=AgentEngineType.OPENHANDS,
                success=False,
                output="",
                error=f"Polling timed out after {timeout_seconds}s",
                duration_seconds=time.monotonic() - start,
                metadata={"conversation_id": conversation_id},
            )
        except Exception as exc:
            return AgentEngineResult(
                engine=AgentEngineType.OPENHANDS,
                success=False,
                output="",
                error=f"Poll request failed: {exc}",
                duration_seconds=time.monotonic() - start,
                metadata={"conversation_id": conversation_id},
            )

    async def is_available(self) -> bool:
        try:
            resp = await self._request("get", "/", timeout=5.0)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, Exception):
            return False

    def get_capabilities(self) -> AgentEngineCapabilities:
        return AgentEngineCapabilities(
            engine_type=AgentEngineType.OPENHANDS,
            max_context_tokens=200_000,
            supports_sandbox=True,
            supports_parallel=True,
            supports_mcp=False,
            supports_streaming=True,
            cost_per_hour_usd=3.0,
        )
