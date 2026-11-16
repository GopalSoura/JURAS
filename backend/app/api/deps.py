from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.simulation.manager import SimulationManager
    from app.ws.frontend_adapter import FrontendWorld

manager: "SimulationManager | None" = None
world: "FrontendWorld | None" = None


def set_runtime(m: "SimulationManager", w: "FrontendWorld") -> None:
    global manager, world
    manager = m
    world = w


def get_manager() -> "SimulationManager":
    assert manager is not None, "runtime not initialised"
    return manager


def get_world() -> "FrontendWorld":
    assert world is not None, "runtime not initialised"
    return world
