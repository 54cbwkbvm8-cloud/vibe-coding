"""Coordinates WorkMode activation and deactivation."""

from __future__ import annotations

from .work_modes import WorkMode


class ModeCoordinator:
    def __init__(self, work_mode: WorkMode) -> None:
        self._current = work_mode

    @property
    def current(self) -> WorkMode:
        return self._current

    def activate(self) -> None:
        self._current.activate()

    def transition_to(
        self,
        work_mode: WorkMode,
        *,
        cancel_request: bool = True,
    ) -> None:
        if work_mode.definition.key == self._current.definition.key:
            self._current = work_mode
            return
        self._current.deactivate(cancel_request=cancel_request)
        self._current = work_mode
        self._current.activate()
