from collections.abc import Callable


class HealthRegistry:
    """Named component checks shared by the host and actuator endpoints."""

    def __init__(self):
        self._checks: dict[str, Callable] = {}

    def add(self, name: str, check: Callable):
        self._checks[name] = check

    def checks(self) -> dict[str, Callable]:
        return dict(self._checks)
