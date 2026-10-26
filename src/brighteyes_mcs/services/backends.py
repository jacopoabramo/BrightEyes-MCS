"""Where the mcs service reads and writes register values."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from brighteyes_mcs.acquisition.manager import McsManager, _pispad23_nifpga_dimension_registers
from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.acquisition.settings import AcquisitionConfig
from brighteyes_mcs.services.registers import RegisterSpec
from brighteyes_mcs.ui.controllers.statistics import scan_duration_seconds

T = TypeVar("T")

#: Processes a run may start, as the manager's supervisor names them.
WORKERS = ("preprocess", "preview")


@dataclass(frozen=True)
class RunStatus:
    """Where a run stands, as the backend sees it.

    Parameters
    ----------
    fifos_complete
        Whether every active FIFO has delivered the elements the run expects.
    workers_alive
        Whether every process the run started is still running.
    """

    done: bool
    almost_done: bool
    fifos_complete: bool
    workers_alive: bool


class RegisterBackend(Protocol):
    """Reads and writes the register values the service serves."""

    async def read(self, names: Sequence[str]) -> dict[str, Any] | None:
        """Return the value of each register, or `None` when the board is busy."""
        ...

    async def write_many(self, values: Mapping[str, Any]) -> None:
        """Write each register of `values`, in order, in one call to the board."""
        ...

    def on_write(self, listener: Callable[[str], None]) -> None:
        """Call `listener` with the register name after each successful write."""
        ...

    async def reset(self) -> None:
        """Send the stop pulse and wait until the scan has stopped."""
        ...

    async def prepare_run(self, config: AcquisitionConfig) -> None:
        """Write the registers of a run in order and prepare what reads its data."""
        ...

    async def run_pipeline(self) -> None:
        """Start the processes that read and store the run's data."""
        ...

    async def start(self) -> None:
        """Send the start pulse."""
        ...

    async def run_status(self) -> RunStatus:
        """Return where the run stands."""
        ...

    async def finish(self) -> str:
        """Stop the scan and the processes of the run; return the file it wrote, or `""`."""
        ...


class TimedRun:
    """A run without a board: its registers go through `write_many`, and it ends on a timer.

    The run is done once the scan's nominal duration has passed since the
    start pulse. It starts no process and writes no file.
    """

    duration: float = 0.0
    started: float | None = None

    async def write_many(self, values: Mapping[str, Any]) -> None:
        raise NotImplementedError

    async def reset(self) -> None:
        await self.write_many({"stop_command": True})
        await self.write_many({"stop_command": False})

    async def prepare_run(self, config: AcquisitionConfig) -> None:
        for registers in run_registers(config):
            await self.write_many(registers)
        circular = config.options.circular_scan
        self.duration = scan_duration_seconds(
            config.timing.time_resolution_us,
            config.timing.timebins_per_pixel,
            config.scan_area.pixels,
            config.scan_area.lines,
            config.scan_area.frames,
            config.scan_area.repetitions,
            circular_points=config.timing.circular_points if circular else 1,
            circular_repetitions=config.timing.circular_repetitions if circular else 1,
        )

    async def run_pipeline(self) -> None:
        pass

    async def start(self) -> None:
        await self.write_many({"stop_command": False, "start_command": True})
        await self.write_many({"start_command": False})
        self.started = time.monotonic()

    async def run_status(self) -> RunStatus:
        done = self.started is not None and time.monotonic() - self.started >= self.duration
        return RunStatus(done=done, almost_done=done, fifos_complete=True, workers_alive=True)

    async def finish(self) -> str:
        await self.reset()
        self.started = None
        return ""


class DictRegisters(TimedRun):
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

    async def write_many(self, values: Mapping[str, Any]) -> None:
        self.values.update(values)
        for name in values:
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

    async def write_many(self, values: Mapping[str, Any]) -> None:
        await self.call(self.manager.set_registers_dict, dict(values))

    async def call(self, function: Callable[..., T], *arguments: Any) -> T:
        """Run `function` with `arguments` on the backend's thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, function, *arguments)

    async def reset(self) -> None:
        await self.call(self.manager.quick_reset_fpga)

    async def prepare_run(self, config: AcquisitionConfig) -> None:
        await self.call(self.manager.prepare_run, config)

    async def run_pipeline(self) -> None:
        await self.call(self.run_pipeline_now)

    def run_pipeline_now(self) -> None:
        # The done events of the run before would otherwise end this one at once.
        self.manager.acquisition_done_reset()
        self.manager.acquisition_almost_done_reset()
        self.manager.run()

    async def start(self) -> None:
        await self.call(self.manager.start)

    async def run_status(self) -> RunStatus:
        return await self.call(self.run_status_now)

    def run_status_now(self) -> RunStatus:
        manager = self.manager
        supervisor = manager.process_supervisor
        # The loop sets the done flag before it exits, so reading the workers
        # first never shows a run that ended normally as a dead worker.
        workers_alive = all(
            supervisor.is_alive(name) for name in WORKERS if supervisor.get(name) is not None
        )
        fifos_complete = all(
            manager.get_current_preview_element(fifo) >= manager.get_expected_fifo_elements(fifo)
            for fifo in manager.activated_fifos_list
        )
        return RunStatus(
            done=manager.acquisition_is_done(),
            almost_done=manager.acquisition_is_almost_done(),
            fifos_complete=fifos_complete,
            workers_alive=workers_alive,
        )

    async def finish(self) -> str:
        return await self.call(self.finish_now)

    def finish_now(self) -> str:
        """Stop the scan, the pipeline and the acquisition, trying each when one before raises.

        Raises
        ------
        Exception
            The first error a step raised, once every step has been tried.
        """
        error: Exception | None = None
        for step in (
            self.manager.quick_reset_fpga,
            self.manager.stop_preview,
            self.manager.stop_acquisition,
        ):
            try:
                step()
            except Exception as failure:
                error = error or failure
        if error is not None:
            raise error
        return str(self.manager.shared_dict.get("filenameh5", ""))

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
