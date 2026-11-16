import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_world
from app.realtime.bus import bus

logger = logging.getLogger("juras.ws")

router = APIRouter(tags=["ws"])


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await bus.connect(websocket, "live")
    try:
        while True:
            raw = await websocket.receive_text()
            if raw in ("ping", "heartbeat"):
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await bus.disconnect(websocket)
    except Exception:
        await bus.disconnect(websocket)


@router.websocket("/ws")
async def ws_frontend(websocket: WebSocket) -> None:
    world = get_world()
    await world.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                cmd = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(cmd, dict):
                continue
            await world.handle_cmd(websocket, cmd)
    except WebSocketDisconnect:
        world.disconnect(websocket)
    except Exception:
        logger.exception("ws error")
        world.disconnect(websocket)
