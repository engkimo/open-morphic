"""Active chat turn cancellation control tests."""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import pytest

from interface.cli.turn_control import ActiveTurnController, TurnCancelledError


@pytest.mark.asyncio
async def test_controller_cancels_only_registered_active_turn() -> None:
    controller = ActiveTurnController()
    started = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def operation() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    controlled = asyncio.create_task(controller.run(operation))
    await started.wait()

    assert controller.has_active_turn is True
    assert controller.cancel_active_turn() is True
    assert controller.cancel_active_turn() is True
    with pytest.raises(TurnCancelledError):
        await controlled

    assert cleaned_up.is_set()
    assert controller.has_active_turn is False
    assert controller.cancel_active_turn() is False


@pytest.mark.asyncio
async def test_controller_does_not_translate_external_caller_cancellation() -> None:
    controller = ActiveTurnController()
    started = asyncio.Event()

    async def operation() -> None:
        started.set()
        await asyncio.Event().wait()

    controlled = asyncio.create_task(controller.run(operation))
    await started.wait()
    controlled.cancel()

    with pytest.raises(asyncio.CancelledError):
        await controlled

    assert controller.has_active_turn is False


@pytest.mark.asyncio
async def test_controller_routes_sigint_to_active_turn_and_restores_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_handlers: list[Any] = []
    monkeypatch.setattr(signal, "getsignal", lambda _signal: signal.SIG_DFL)
    monkeypatch.setattr(
        signal,
        "signal",
        lambda _signal, handler: installed_handlers.append(handler),
    )
    controller = ActiveTurnController()
    started = asyncio.Event()

    async def operation() -> None:
        started.set()
        await asyncio.Event().wait()

    controlled = asyncio.create_task(controller.run(operation))
    await started.wait()
    active_handler = installed_handlers[0]

    active_handler(signal.SIGINT, None)

    with pytest.raises(TurnCancelledError):
        await controlled
    assert installed_handlers[-1] == signal.SIG_DFL
