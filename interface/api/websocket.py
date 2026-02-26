"""WebSocket endpoint for real-time task updates."""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from interface.api.schemas import TaskResponse


async def task_ws(websocket: WebSocket, task_id: str) -> None:
    """Poll task state every 1s and send JSON snapshots until complete."""
    await websocket.accept()
    container = websocket.app.state.container

    try:
        last_snapshot: str | None = None
        while True:
            task = await container.task_repo.get_by_id(task_id)
            if task is None:
                await websocket.send_json({"error": f"Task {task_id} not found"})
                break

            data = json.loads(TaskResponse.from_task(task).model_dump_json())

            # Include background planner recommendations if available
            if hasattr(container, "background_planner"):
                recs = container.background_planner.get_recommendations(task_id)
                if recs:
                    data["recommendations"] = recs

            snapshot = json.dumps(data, sort_keys=True)
            # Only send if state changed
            if snapshot != last_snapshot:
                await websocket.send_text(snapshot)
                last_snapshot = snapshot

            if task.is_complete:
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
