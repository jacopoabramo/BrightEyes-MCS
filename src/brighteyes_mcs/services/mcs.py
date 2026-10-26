"""The mcs service: the registers of the board, served as FastCS attributes."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrRW, AttrW
from fastcs.controllers import Controller
from fastcs.datatypes import Bool

from brighteyes_mcs.logging_setup import logger
from brighteyes_mcs.services.backends import RegisterBackend
from brighteyes_mcs.services.registers import RegisterSpec

#: Seconds between two reads of the indicator registers.
INDICATOR_PERIOD: Final = 0.5


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
        try:
            await self.backend.write(attr.io_ref.name, value)
        except Exception:
            await self.read_back(attr.io_ref.name)
            raise


class McsController(Controller):
    """Serves each register of `specs` under the `registers` sub-controller.

    A register's attribute is refreshed after each write the backend reports,
    from any thread, and indicators are read again every `INDICATOR_PERIOD`
    seconds.
    """

    def __init__(
        self, specs: Sequence[RegisterSpec], backend: RegisterBackend, *, simulated: bool
    ) -> None:
        super().__init__(description="BrightEyes-MCS board registers")
        self.backend = backend
        self.indicators = [spec.name for spec in specs if not spec.writable]
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tasks: set[asyncio.Task[None]] = set()
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
            loop.call_soon_threadsafe(self.start, self.read_back(name))

    def start(self, coroutine: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def read_back(self, name: str) -> None:
        """Refresh one register, logging a read that fails."""
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
                await self.refresh(self.indicators)
            except Exception:
                if not failing:
                    logger.warning("Reading the indicator registers failed", exc_info=True)
                failing = True
            else:
                if failing:
                    logger.info("Reading the indicator registers works again")
                failing = False
