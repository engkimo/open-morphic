"""SSE endpoint for real-time task event streaming (TD-161).

Replaces the polling WebSocket for live task updates. The engine pushes
events to TaskEventBus; this endpoint subscribes and streams them as
Server-Sent Events to the browser.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from interface.api.schemas import TaskResponse

router = APIRouter()

HEARTBEAT_INTERVAL = 15  # seconds
MAX_STREAM_DURATION = 3600  # 1 hour — inactivity timeout, not total


@router.get("/api/tasks/{task_id}/stream")
async def stream_task_events(task_id: str, request: Request) -> StreamingResponse:
    """SSE stream of task execution events.

    Event types sent:
      - snapshot: full task state (sent on connect)
      - subtask_started: {subtask_id, description, dependencies}
      - subtask_completed: {subtask_id, status, result, model_used, engine_used, cost_usd}
      - task_started: {status, subtask_count, subtasks}
      - task_completed: {status, total_cost_usd}
      - reflection_started: {round}
      - node_spawned: {subtask_id, description, spawned_by, reflection_round}
      - reflection_complete: {satisfied, spawned_count}
      - heartbeat: keep-alive (comment line)
    """
    container = request.app.state.container

    async def event_generator():  # noqa: C901
        # 1. Send initial snapshot
        task = await container.task_repo.get_by_id(task_id)
        if task is None:
            yield _sse("error", {"message": f"Task {task_id} not found"})
            return

        snapshot = json.loads(TaskResponse.from_task(task).model_dump_json())
        yield _sse("snapshot", snapshot)

        # If already complete, nothing to stream
        if task.is_complete:
            yield _sse("task_completed", {
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "total_cost_usd": task.total_cost_usd,
            })
            return

        # 2. Subscribe to event bus
        queue = container.event_bus.subscribe(task_id)
        try:
            elapsed = 0.0
            while elapsed < MAX_STREAM_DURATION:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                    event_type = event.pop("type", "update")
                    yield _sse(event_type, event)

                    # Stop streaming after task completion
                    if event_type == "task_completed":
                        # Send final snapshot so UI has complete state
                        final = await container.task_repo.get_by_id(task_id)
                        if final:
                            final_data = json.loads(TaskResponse.from_task(final).model_dump_json())
                            yield _sse("snapshot", final_data)
                        break

                    # Reset inactivity timer — execution is still alive
                    elapsed = 0.0
                except TimeoutError:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
                    elapsed += HEARTBEAT_INTERVAL
        finally:
            container.event_bus.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _sse(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"
