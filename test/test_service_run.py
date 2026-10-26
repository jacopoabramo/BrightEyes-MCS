"""Pin how the mcs service starts, ends, stops and guards a run."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import nifpga
import pytest

from brighteyes_mcs.services.backends import DictRegisters, RegisterBackend, RunStatus
from brighteyes_mcs.services.mcs import McsController
from brighteyes_mcs.services.registers import RegisterSpec, register_specs
from test.fake_bitfile import SERVICE_REGISTERS, fake_bitfile_xml
from test.test_service_controller import StubBackend
from test.test_service_settings import SlowRegisters, held, window_registers
from test.window_settings import window_config

#: Repetitions that keep a simulated run going far longer than any test.
LONG_RUN = 10**6


def run_specs() -> list[RegisterSpec]:
    """Return the specs of a fake bitfile holding the settings and run registers."""
    return register_specs(
        nifpga.Bitfile(fake_bitfile_xml(SERVICE_REGISTERS), parse_contents=True), {}
    )


def quick_registers() -> dict[str, Any]:
    """Return the window's register values over a 4 by 4 grid of one frame."""
    return {**window_registers(), "max_pixel": 4, "max_line": 4, "max_frame": 1}


def serve_run(backend: RegisterBackend, body: Callable[[McsController], Awaitable[None]]) -> None:
    """Connect a controller serving runs over `backend`, run `body`, then disconnect."""
    controller = McsController(
        run_specs(), backend, simulated=True, held=held(), detector=window_config().detector
    )
    controller.post_initialise()

    async def main() -> None:
        await controller.connect()
        try:
            await body(controller)
        finally:
            await controller.disconnect()

    asyncio.run(main())


async def start_long_run(controller: McsController) -> None:
    """Start a run that saves nothing and lasts longer than any test."""
    await controller.run.save.put(False)
    await controller.run.repetitions.put(LONG_RUN)
    await controller.run.start()


class FailingStatus(DictRegisters):
    """Registers in a dictionary whose run status cannot be read."""

    async def run_status(self) -> RunStatus:
        raise RuntimeError("status lost")


class DeadWorker(DictRegisters):
    """Registers in a dictionary whose run reports its workers stopped before it is done."""

    async def run_status(self) -> RunStatus:
        return RunStatus(done=False, almost_done=False, fifos_complete=False, workers_alive=False)


def test_a_run_writes_its_registers_and_ends_by_itself() -> None:
    """Write the run registers and the start pulse, then end the run and count it."""
    backend = DictRegisters(run_specs(), quick_registers())
    written: list[str] = []
    backend.on_write(written.append)

    async def body(controller: McsController) -> None:
        await controller.run.save.put(False)
        await controller.run.start()
        assert controller.run.running.get() is True

        await controller.run.running.wait_for_value(False, timeout=2)

        assert controller.run.completed.get() == 1
        assert controller.run.last_error.get() == ""

    serve_run(backend, body)

    assert "start_command" in written
    assert backend.values["start_command"] is False
    assert backend.values["max_repetition"] == 2
    assert backend.values["dfd_trigger_selector"] == 5


def test_stop_ends_a_run_without_counting_it() -> None:
    """End a run in progress on stop, leaving completed at zero."""
    backend = DictRegisters(run_specs(), quick_registers())

    async def body(controller: McsController) -> None:
        await start_long_run(controller)

        await controller.run.stop()

        assert controller.run.running.get() is False
        assert controller.run.completed.get() == 0

    serve_run(backend, body)


def test_a_second_start_and_a_start_without_a_file_are_refused() -> None:
    """Refuse a start while a run is in progress, and a saving start with no file name."""
    backend = DictRegisters(run_specs(), quick_registers())

    async def body(controller: McsController) -> None:
        with pytest.raises(ValueError):
            await controller.run.start()
        assert controller.run.running.get() is False

        await start_long_run(controller)
        with pytest.raises(RuntimeError, match="a run is in progress"):
            await controller.run.start()

    serve_run(backend, body)


def test_stop_sent_while_start_prepares_ends_the_run() -> None:
    """End the run that start began when stop arrives during its prepare."""
    backend = SlowRegisters(run_specs(), quick_registers())

    async def body(controller: McsController) -> None:
        await controller.run.save.put(False)
        await controller.run.repetitions.put(LONG_RUN)

        await asyncio.gather(controller.run.start(), controller.run.stop())

        assert controller.run.running.get() is False
        assert controller.run.completed.get() == 0

    serve_run(backend, body)


def test_a_refused_prepare_raises_and_records_the_error() -> None:
    """Raise the board's refusal of a prepare, record it, and leave no run in progress."""
    backend = StubBackend(quick_registers(), write_error=RuntimeError("board said no"))

    async def body(controller: McsController) -> None:
        await controller.run.save.put(False)

        with pytest.raises(RuntimeError, match="board said no"):
            await controller.run.start()

        assert "board said no" in controller.run.last_error.get()
        assert controller.run.running.get() is False

    serve_run(backend, body)


def test_a_status_that_fails_ends_the_run_with_its_error() -> None:
    """End the run and record the error when reading the run status raises."""
    backend = FailingStatus(run_specs(), quick_registers())

    async def body(controller: McsController) -> None:
        await controller.run.save.put(False)
        await controller.run.start()

        await controller.run.running.wait_for_value(False, timeout=2)

        assert "status lost" in controller.run.last_error.get()

    serve_run(backend, body)


def test_a_worker_that_stops_ends_the_run_with_an_error() -> None:
    """End the run and record that the worker stopped when the workers die before done."""
    backend = DeadWorker(run_specs(), quick_registers())

    async def body(controller: McsController) -> None:
        await controller.run.save.put(False)
        await controller.run.start()

        await controller.run.running.wait_for_value(False, timeout=2)

        assert controller.run.last_error.get() == "the acquisition worker stopped"
        assert controller.run.completed.get() == 0

    serve_run(backend, body)
