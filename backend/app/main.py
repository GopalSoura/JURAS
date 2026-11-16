from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import set_runtime
from app.api.v1.endpoints import health as health_endpoint
from app.api.v1.router import api_router
health_router = health_endpoint.router
from app.core.config import settings
from app.core.exceptions import AppError, app_error_handler, unhandled_error_handler
from app.core.logging import setup_logging
from app.db.session import SessionFactory, check_db, dispose_engine
from app.realtime.bus import bus
from app.simulation.manager import SimulationManager
from app.ws.frontend_adapter import FrontendWorld
from app.ws.ws_routes import router as ws_router

setup_logging()

runtime: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = SimulationManager(SessionFactory)
    world = FrontendWorld(SessionFactory, manager)
    bus.set_adapter_handler(world.handle_event)
    set_runtime(manager, world)
    runtime["manager"] = manager
    runtime["world"] = world
    ok = await check_db()
    if not ok:
        import logging

        logging.getLogger("juras").warning("Database not reachable at startup")
    yield
    await manager.shutdown()
    task = world._telemetry_task
    if task is not None:
        task.cancel()
    bus.set_adapter_handler(None)
    await dispose_engine()


app = FastAPI(
    title="JURAS API",
    version="1.0.0",
    description="Jammu Urban Risk Intelligence System - simulation-first prototype. "
    "All readings and risk scores are synthetic demo values, never real observations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return await app_error_handler(request, AppError("VALIDATION_ERROR", "Invalid request payload", 422))


app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix="/api/v1")
app.include_router(health_router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict:
    return {"project": "JURAS", "pilot": "Purani Mandi", "status": "running", "docs": "/docs"}
