"""The mcs service: the registers of the board, served as FastCS attributes."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import faulthandler
import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

import nifpga
from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrRW, AttrW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Bool
from fastcs.transports.epics.pva.transport import EpicsPVATransport
from redsun.services import configure_logging, identity, ready_when_reachable, wait_for_stop

from brighteyes_mcs.acquisition.detectors.models import DETECTOR_SPAD_ARRAY
from brighteyes_mcs.acquisition.manager import DEFAULT_REGISTERS, McsManager
from brighteyes_mcs.logging_setup import logger
from brighteyes_mcs.services.backends import DictRegisters, ManagerRegisters, RegisterBackend
from brighteyes_mcs.services.registers import (
    NO_DESCRIPTION,
    RegisterSpec,
    WholeFloat,
    load_descriptions,
    register_specs,
)

#: Seconds between two reads of the indicator registers.
INDICATOR_PERIOD: Final = 0.5

#: Seconds the board may take to stop once the service is asked to. A session
#: kills a service 10 s after asking it to stop.
STOP_DEADLINE: Final = 8.0

#: Seconds the service may take to become ready, or to stop serving, before it
#: writes every thread's stack to its output. Below the 15 s a session waits
#: for readiness, so the stacks reach the session's log.
TRACEBACK_DELAY: Final = 10.0


@dataclass
class RegisterRef(AttributeIORef):
    """Names the register an attribute serves."""

    name: str = ""


class RegisterIO(AttributeIO[Any, RegisterRef]):
    """Writes an attribute's register through the backend."""

    def __init__(
        self, backend: RegisterBackend, read_back: Callable[[str], Awaitable[None]]
    ) -> None:
        super().__init__()
        self.backend = backend
        self.read_back = read_back

    async def update(self, attr: AttrR[Any, RegisterRef]) -> None:
        await self.read_back(attr.io_ref.name)

    async def send(self, attr: AttrW[Any, RegisterRef], value: Any) -> None:
        """Write `value`; when the board refuses it, show what the register holds and raise."""
        if isinstance(attr.datatype, WholeFloat):
            # The attribute holds a double, but the board takes only integers.
            value = int(value)
        try:
            await self.backend.write(attr.io_ref.name, value)
        except Exception:
            await self.read_back(attr.io_ref.name)
            raise


class McsController(Controller):
    """Serves each register of `specs` under the `registers` sub-controller.

    A register's attribute is refreshed after each write the backend reports,
    from any thread, and indicators are read again every `INDICATOR_PERIOD`
    seconds. A written register whose read-back found the board busy is read
    again with the indicators until a read succeeds.
    """

    def __init__(
        self, specs: Sequence[RegisterSpec], backend: RegisterBackend, *, simulated: bool
    ) -> None:
        super().__init__(description="BrightEyes-MCS board registers")
        self.backend = backend
        self.indicators = [spec.name for spec in specs if not spec.writable]
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tasks: set[asyncio.Task[None]] = set()
        self.pending: set[str] = set()
        self.simulated = AttrR(Bool(), initial_value=simulated)
        self.registers = Controller(ios=[RegisterIO(backend, self.read_back)])
        for spec in specs:
            kind = AttrRW if spec.writable else AttrR
            attribute = kind(
                spec.datatype, io_ref=RegisterRef(name=spec.name), description=spec.description
            )
            self.registers.add_attribute(spec.name, attribute)

    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.backend.on_write(self.written)
        await self.refresh(list(self.registers.attributes))
        self.start(self.poll_indicators())
        await super().connect()

    async def disconnect(self) -> None:
        self.loop = None
        for task in list(self.tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def written(self, name: str) -> None:
        """Schedule a read-back of a register the backend wrote, from any thread."""
        loop = self.loop
        if loop is None:
            return
        # The loop can close between the check and the call while the service stops.
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self.read_back_soon, name)

    def read_back_soon(self, name: str) -> None:
        self.start(self.read_back(name))

    def start(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def read_back(self, name: str) -> None:
        """Refresh one register, logging a read that fails.

        The register is read again with the indicators until a read returns it.
        """
        self.pending.add(name)
        try:
            await self.refresh([name])
        except Exception:
            logger.exception("Reading back register %r failed", name)

    async def refresh(self, names: Sequence[str]) -> None:
        """Update the attributes of `names` from one read of the backend.

        Nothing is updated when the backend is busy. A value an attribute
        refuses is logged and the other attributes still update.
        """
        values = await self.backend.read(names)
        if values is None:
            return
        self.pending.difference_update(values)
        for name, value in values.items():
            try:
                await self.registers.attributes[name].update(value)
            except Exception:
                logger.exception("Register %r refused the value %r read back", name, value)

    async def poll_indicators(self) -> None:
        failing = False
        while True:
            await asyncio.sleep(INDICATOR_PERIOD)
            try:
                await self.refresh([*self.indicators, *self.pending])
            except Exception:
                if not failing:
                    logger.warning("Reading the indicator registers failed", exc_info=True)
                failing = True
            else:
                if failing:
                    logger.info("Reading the indicator registers works again")
                failing = False


def parse_options(argv: Sequence[str] | None) -> argparse.Namespace:
    """Return the options of the service; the name and prefix default to the session's."""
    service = identity()
    parser = argparse.ArgumentParser(
        prog="python -m brighteyes_mcs.services.mcs",
        description="Serve the registers of a BrightEyes-MCS board over PVAccess.",
    )
    parser.add_argument("--bitfile", required=True, help="bitfile the board runs")
    parser.add_argument("--resource", default="RIO0", help="NI resource name of the board")
    parser.add_argument(
        "--detector-model", default=DETECTOR_SPAD_ARRAY, help="detector the board drives"
    )
    parser.add_argument(
        "--simulate", action="store_true", help="hold the registers in memory, without a board"
    )
    parser.add_argument(
        "--prefix", default=service.prefix if service else "", help="PV prefix of the service"
    )
    parser.add_argument(
        "--name", default=service.name if service else "mcs", help="name of the service"
    )
    return parser.parse_args(argv)


async def serve(controller: McsController, prefix: str) -> None:
    """Serve `controller` over PVAccess until the session, or Ctrl+C, stops the service.

    Raises
    ------
    Exception
        The error that ended serving before the stop, such as a controller
        that failed to connect.
    """
    faulthandler.dump_traceback_later(TRACEBACK_DELAY)
    controller.set_path([prefix])
    control_system = FastCS(controller, [EpicsPVATransport()])
    serve_task = asyncio.ensure_future(control_system.serve(interactive=False))
    ready_task = asyncio.ensure_future(ready_when_reachable(f"{prefix}:PVI"))
    ready_task.add_done_callback(lambda _: faulthandler.cancel_dump_traceback_later())
    stop_task = asyncio.ensure_future(wait_for_stop())
    try:
        await asyncio.wait({serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if serve_task.done():
            serve_task.result()
    finally:
        faulthandler.dump_traceback_later(TRACEBACK_DELAY)
        for task in (ready_task, serve_task, stop_task):
            task.cancel()
        await asyncio.gather(serve_task, ready_task, stop_task, return_exceptions=True)
        faulthandler.cancel_dump_traceback_later()


def stop_board(manager: McsManager | None, deadline: float) -> bool:
    """Stop the board and the manager's processes, waiting at most `deadline` seconds.

    The stop runs on a daemon thread, so a stop that hangs cannot keep the
    process alive. Past the deadline every thread's stack is written to the
    output and an error is logged.

    Returns
    -------
    bool
        Whether the stop finished in time; `True` without a manager.
    """
    if manager is None:
        return True

    def stop() -> None:
        try:
            try:
                manager.stop_fpga()
            finally:
                manager.mp_manager.shutdown()
        except Exception:
            logger.exception("Stopping the board failed")

    worker = threading.Thread(target=stop, name="stop-board", daemon=True)
    worker.start()
    worker.join(deadline)
    if worker.is_alive():
        faulthandler.dump_traceback(all_threads=True)
        logger.error("The board did not stop within %s s", deadline)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """Serve the registers of the board until the session stops the service.

    Returns 1 when the bitfile cannot be read, the board cannot be connected
    or serving ends with an error, and 0 once the service has stopped.
    """
    configure_logging()
    options = parse_options(argv)
    try:
        bitfile = nifpga.Bitfile(options.bitfile)
    except Exception:
        logger.exception("Cannot read the bitfile %s", options.bitfile)
        return 1
    specs = register_specs(bitfile, load_descriptions())
    undescribed = [spec.name for spec in specs if spec.description == NO_DESCRIPTION]
    if undescribed:
        logger.info("Registers without a description: %s", ", ".join(undescribed))

    manager = None
    backend: RegisterBackend
    if options.simulate:
        backend = DictRegisters(specs, DEFAULT_REGISTERS)
    else:
        manager = McsManager(filename=options.bitfile, address=options.resource)
        manager.set_detector_model(options.detector_model)
        try:
            manager.connect(dict(DEFAULT_REGISTERS))
        except Exception:
            logger.exception("Cannot connect to the board at %s", options.resource)
            stop_board(manager, STOP_DEADLINE)
            return 1
        backend = ManagerRegisters(manager)

    controller = McsController(specs, backend, simulated=options.simulate)
    try:
        # Ctrl+C, the way a service run on its own is stopped, is a clean stop.
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve(controller, options.prefix.rstrip(":") or options.name))
    except Exception:
        logger.exception("Serving the registers failed")
        return 1
    finally:
        stop_board(manager, STOP_DEADLINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
