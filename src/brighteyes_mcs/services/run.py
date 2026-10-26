"""The run of the mcs service: its settings, its commands and what it reports."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final

from fastcs.attributes import AttrR, AttrRW
from fastcs.controllers import Controller
from fastcs.datatypes import Bool, Int, String
from fastcs.methods import command

from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.acquisition.settings import DetectorConfig
from brighteyes_mcs.logging_setup import logger
from brighteyes_mcs.services.backends import RegisterBackend
from brighteyes_mcs.services.physical import (
    RunSettings,
    Settings,
    guarded_registers,
    held_during_run,
    run_config,
)
from brighteyes_mcs.services.settings import SettingIO, SettingRef

#: Seconds between two reads of the run's status.
STATUS_PERIOD: Final = 0.5

#: Seconds a run waits, once done, for its FIFOs to deliver what it expects.
DONE_GRACE: Final = 5.0

#: Seconds the service waits for a run in progress to end when it stops.
SHUTDOWN_DEADLINE: Final = 2.0

RUN_IN_PROGRESS: Final = "a run is in progress"
WORKER_STOPPED: Final = "the acquisition worker stopped"


class RunController(Controller):
    """Starts, watches and stops a run of the scan, and refuses writes that would change it.

    A run is prepared from the settings that `settings` returns and from the
    run settings `repetitions`, `filename` and `save`. Every command and put
    holds `lock`, the lock the settings and register puts hold, so a put never
    lands in the middle of a start. `show_written` reads back the registers a
    start wrote.
    """

    def __init__(
        self,
        backend: RegisterBackend,
        lock: asyncio.Lock,
        settings: Callable[[], Settings],
        detector: DetectorConfig,
        show_written: Callable[[Mapping[str, Any]], Awaitable[None]],
    ) -> None:
        super().__init__(description="A run of the scan", ios=[SettingIO(self.put)])
        self.backend = backend
        self.lock = lock
        self.settings = settings
        self.detector = detector
        self.show_written = show_written
        self.guarded = guarded_registers()
        self.watch_task: asyncio.Task[None] | None = None
        self.repetitions = AttrRW(
            Int(min=1), io_ref=SettingRef(path="repetitions"), initial_value=1
        )
        self.filename = AttrRW(String(), io_ref=SettingRef(path="filename"), initial_value="")
        self.save = AttrRW(Bool(), io_ref=SettingRef(path="save"), initial_value=True)
        self.running = AttrR(Bool(), initial_value=False)
        self.almost_done = AttrR(Bool(), initial_value=False)
        self.completed = AttrR(Int(), initial_value=0)
        self.last_filename = AttrR(String(), initial_value="")
        self.last_error = AttrR(String(), initial_value="")
        self.board_responding = AttrR(Bool(), initial_value=True)

    async def put(self, name: str, value: Any) -> None:
        """Set the run setting `name`.

        Raises
        ------
        RuntimeError
            While a run is in progress.
        """
        async with self.lock:
            if self.running.get():
                raise RuntimeError(RUN_IN_PROGRESS)
            await getattr(self, name).update(value)

    def check_setting(self, path: str) -> None:
        """Refuse a put of the setting `path` while a run holds it.

        Raises
        ------
        RuntimeError
            While a run is in progress and holds the setting.
        """
        if self.running.get() and held_during_run(path):
            raise RuntimeError(RUN_IN_PROGRESS)

    def check_register(self, name: str) -> None:
        """Refuse a raw put of the register `name` while a run holds it.

        Raises
        ------
        RuntimeError
            While a run is in progress and holds the register.
        """
        if self.running.get() and name in self.guarded:
            raise RuntimeError(RUN_IN_PROGRESS)

    @command()
    async def start(self) -> None:
        """Prepare and start a run, returning once the start pulse is written.

        Raises
        ------
        RuntimeError
            While a run is in progress.
        ValueError
            When `save` is on and `filename` is empty.
        """
        async with self.lock:
            if self.running.get():
                raise RuntimeError(RUN_IN_PROGRESS)
            if self.save.get() and not self.filename.get():
                raise ValueError("save is on but no file name is set")
            await self.running.update(True)
            await self.almost_done.update(False)
            await self.last_error.update("")
            try:
                await self.backend.reset()
                run = RunSettings(self.repetitions.get(), self.filename.get(), self.save.get())
                config = run_config(self.settings(), run, self.detector)
                await self.backend.prepare_run(config)
                await self.backend.run_pipeline()
                await self.backend.start()
                written = {
                    name: value for group in run_registers(config) for name, value in group.items()
                }
                await self.show_written({**written, "start_command": False, "stop_command": False})
            except Exception as error:
                await self.end(completed=False, error=str(error) or repr(error))
                raise
        self.watch_task = asyncio.ensure_future(self.watch())

    @command()
    async def stop(self) -> None:
        """End a run in progress early; do nothing when there is none."""
        async with self.lock:
            if not self.running.get():
                return
            if self.watch_task is not None:
                self.watch_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.watch_task
            await self.end(completed=False)

    @command()
    async def reset(self) -> None:
        """Send the stop pulse and wait until the scan has stopped.

        Raises
        ------
        RuntimeError
            While a run is in progress.
        """
        async with self.lock:
            if self.running.get():
                raise RuntimeError(RUN_IN_PROGRESS)
            await self.backend.reset()

    async def watch(self) -> None:
        """Poll the run's status until it ends, then end it."""
        done_at: float | None = None
        while True:
            await asyncio.sleep(STATUS_PERIOD)
            try:
                status = await self.backend.run_status()
            except Exception as error:
                await self.end_watched(completed=False, error=str(error) or repr(error))
                return
            await self.almost_done.update(status.almost_done)
            if status.done:
                if done_at is None:
                    done_at = time.monotonic()
                if status.fifos_complete or time.monotonic() - done_at >= DONE_GRACE:
                    await self.end_watched(completed=True)
                    return
            elif not status.workers_alive:
                await self.end_watched(completed=False, error=WORKER_STOPPED)
                return

    async def end_watched(self, *, completed: bool, error: str = "") -> None:
        """End the run the watch found over, unless a stop ended it first."""
        async with self.lock:
            if self.running.get():
                await self.end(completed=completed, error=error)

    async def end(self, *, completed: bool, error: str = "") -> None:
        """Stop the scan and the run's processes and report how the run ended.

        Call with the lock held. A run counts as completed only when it ended
        normally and `finish` succeeded.
        """
        filename = ""
        try:
            filename = await self.backend.finish()
        except Exception as failure:
            logger.exception("Ending the run failed")
            error = error or str(failure) or repr(failure)
        if completed and not error:
            await self.completed.update(self.completed.get() + 1)
            if self.save.get():
                await self.last_filename.update(filename)
        if error:
            logger.warning("The run ended abnormally: %s", error)
        await self.last_error.update(error)
        await self.running.update(False)

    async def shutdown(self) -> None:
        """End a run in progress, waiting at most `SHUTDOWN_DEADLINE` seconds."""
        try:
            await asyncio.wait_for(self.stop(), SHUTDOWN_DEADLINE)
        except TimeoutError:
            logger.error("The run did not end within %s s", SHUTDOWN_DEADLINE)
