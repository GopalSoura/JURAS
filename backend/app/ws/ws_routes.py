import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketDisconnected

from app.api.deps import get_world
from app.realtime.bus import bus

logger = logging.getLogger("juras.ws")

router = APIRouter(tags=["ws"])

# A client can vanish at any point (page reload, Vite HMR, network drop). Starlette
# raises WebSocketDisconnected (a RuntimeError) when the socket is used after a
# failed send marked it disconnected, so both exceptions mean "client is gone".
DISCONNECTS = (WebSocketDisconnect, WebSocketDisconnected)


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    try:
        await bus.connect(websocket, "live")
        while True:
            raw = await websocket.receive_text()
            if raw in ("ping", "heartbeat"):
                await websocket.send_text("pong")
    except DISCONNECTS:
        pass
    except Exception:
        logger.exception("ws/live error")
    finally:
        await bus.disconnect(websocket)


@router.websocket("/ws")
async def ws_frontend(websocket: WebSocket) -> None:
    world = get_world()
    try:
        if not await world.connect(websocket):
            return
        while True:
            raw = await websocket.receive_text()
            try:
                cmd = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(cmd, dict):
                continue
            await world.handle_cmd(websocket, cmd)
    except DISCONNECTS:
        pass
    except Exception:
        logger.exception("ws error")
    finally:
        world.disconnect(websocket)
