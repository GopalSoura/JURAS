from typing import Any, Protocol


class ScenarioModel(Protocol):
    name: str

    def initial_state(self, config: dict[str, Any]) -> dict[str, Any]: ...

    def next_reading(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> dict[str, Any]: ...

    def is_finished(self, state: dict[str, Any], elapsed_sec: float, config: dict[str, Any]) -> bool: ...


SEVERITY_RATE = {"normal": 0.55, "warning": 1.0, "critical": 1.6}
