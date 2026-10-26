"""Where the mcs service reads and writes register values."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from brighteyes_mcs.acquisition.manager import McsManager, _pispad23_nifpga_dimension_registers
from brighteyes_mcs.services.registers import RegisterSpec


class RegisterBackend(Protocol):
    """Reads and writes the register values the service serves."""

    async def read(self, names: Sequence[str]) -> dict[str, Any] | None:
        """Return the value of each register, or `None` when the board is busy."""
        ...

    async def write(self, name: str, value: Any) -> None:
        """Write one register."""
        ...

    def on_write(self, listener: Callable[[str], None]) -> None:
        """Call `listener` with the register name after each successful write."""
        ...


class DictRegisters:
    """Registers held in a dictionary, for running the service without a board.

    Each register starts from its datatype's initial value, overlaid by the
    entries of `initial` that name a register and hold a value other than
    `None`, which the manager's defaults use for a register they leave unset.
    """

    def __init__(self, specs: Sequence[RegisterSpec], initial: Mapping[str, Any]) -> None:
        self.values: dict[str, Any] = {spec.name: spec.datatype.initial_value for spec in specs}
        self.values.update(
            (name, value)
            for name, value in initial.items()
            if name in self.values and value is not None
        )
        self.listeners: list[Callable[[str], None]] = []

    async def read(self, names: Sequence[str]) -> dict[str, Any] | None:
        return {name: self.values[name] for name in names}

    async def write(self, name: str, value: Any) -> None:
        self.values[name] = value
        for listener in self.listeners:
            listener(name)

    def on_write(self, listener: Callable[[str], None]) -> None:
        self.listeners.append(listener)


class ManagerRegisters:
    """Registers of the board an `McsManager` holds.

    This is the only place the service calls the synchronous manager: each
    call runs on a thread pool the backend owns, so the event loop never waits
    on the board, and a call stuck on the board does not keep the loop from
    closing, as one on the loop's default pool would.
    """

    def __init__(self, manager: McsManager) -> None:
        self.manager = manager
        self.executor = ThreadPoolExecutor(thread_name_prefix="mcs-board")

    async def read(self, names: Sequence[str]) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.read_now, list(names))

    def read_now(self, names: list[str]) -> dict[str, Any] | None:
        with self.manager.fpga_access(wait=False) as acquired:
            handle = self.manager.fpga_handle
            if not acquired or not self.manager.is_connected or handle is None:
                return None
            values = handle.register_read(names)
            # The manager adds an offset to some dimensions on write for
            # PISPAD23 detectors, so a read removes it to return what was set.
            return _pispad23_nifpga_dimension_registers(
                values, self.manager.detector_model, direction=-1
            )

    async def write(self, name: str, value: Any) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.executor, self.manager.set_registers_dict, {name: value})

    def on_write(self, listener: Callable[[str], None]) -> None:
        """Call `listener` after each write the manager's FPGA handle makes.

        Raises
        ------
        RuntimeError
            If the manager is not connected, so it has no FPGA handle yet.
        """
        if self.manager.fpga_handle is None:
            raise RuntimeError("The FPGA is not connected.")
        self.manager.fpga_handle.add_write_listener(listener)
