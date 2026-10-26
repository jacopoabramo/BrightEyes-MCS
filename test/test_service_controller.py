"""Pin how the mcs service controller keeps its attributes in step with the registers."""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import nifpga
import pytest
from fastcs.attributes import AttrR, AttrRW, AttrW

from brighteyes_mcs.services import mcs
from brighteyes_mcs.services.backends import DictRegisters, RegisterBackend
from brighteyes_mcs.services.mcs import INDICATOR_PERIOD, McsController, serve
from brighteyes_mcs.services.registers import RegisterSpec, register_specs
from test.fake_bitfile import fake_bitfile_xml


class StubBackend:
    """Backend whose reads return fixed values, fail, or find the board busy, by read number."""

    def __init__(
        self,
        values: dict[str, Any],
        *,
        failing_reads: range = range(0),
        busy_reads: range = range(0),
        write_error: Exception | None = None,
    ) -> None:
        self.values = values
        self.failing_reads = failing_reads
        self.busy_reads = busy_reads
        self.write_error = write_error
        self.reads = 0
        self.written: list[dict[str, Any]] = []
        self.listeners: list[Callable[[str], None]] = []

    async def read(self, names: Sequence[str]) -> dict[str, Any] | None:
        self.reads += 1
        if self.reads in self.failing_reads:
            raise RuntimeError("board did not answer")
        if self.reads in self.busy_reads:
            return None
        return {name: value for name, value in self.values.items() if name in names}

    async def write_many(self, values: Mapping[str, Any]) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.written.append(dict(values))

    def on_write(self, listener: Callable[[str], None]) -> None:
        self.listeners.append(listener)


def fake_specs() -> list[RegisterSpec]:
    """Return the specs of the fake bitfile."""
    return register_specs(nifpga.Bitfile(fake_bitfile_xml(), parse_contents=True), {})


def serve_controller(backend: RegisterBackend, body: Callable[[McsController], Awaitable[None]]) -> None:
    """Connect a controller over `backend`, run `body` on it, then disconnect it."""
    controller = McsController(fake_specs(), backend, simulated=True)
    controller.post_initialise()

    async def main() -> None:
        await controller.connect()
        try:
            await body(controller)
        finally:
            await controller.disconnect()

    asyncio.run(main())


def test_controls_are_writable_and_indicators_read_only() -> None:
    """Serve controls as read-write attributes, indicators as read-only ones, and the mode."""

    async def body(controller: McsController) -> None:
        attributes = controller.registers.attributes
        assert isinstance(attributes["max_pixel"], AttrRW)
        assert isinstance(attributes["current_x_index"], AttrR)
        assert not isinstance(attributes["current_x_index"], AttrW)
        assert controller.attributes["simulated"].get() is True

    serve_controller(DictRegisters(fake_specs(), {}), body)


def test_a_put_reaches_the_backend_and_reads_back() -> None:
    """Write a put value to the backend and show the value read back."""
    backend = DictRegisters(fake_specs(), {})

    async def body(controller: McsController) -> None:
        attribute = controller.registers.attributes["max_pixel"]
        await attribute.put(9)
        assert backend.values["max_pixel"] == 9
        await attribute.wait_for_value(9, timeout=0.5)

    serve_controller(backend, body)


def test_a_write_from_elsewhere_reaches_its_attribute() -> None:
    """Show a register written from another thread, as the manager writes, in its attribute."""
    backend = DictRegisters(fake_specs(), {})

    async def body(controller: McsController) -> None:
        writer = threading.Thread(target=lambda: asyncio.run(backend.write_many({"max_pixel": 4})))
        writer.start()
        writer.join()
        await controller.registers.attributes["max_pixel"].wait_for_value(4, timeout=0.5)

    serve_controller(backend, body)


def test_an_indicator_follows_the_backend_within_one_pass() -> None:
    """Show a changed indicator within one polling pass."""
    backend = DictRegisters(fake_specs(), {})

    async def body(controller: McsController) -> None:
        backend.values["current_x_index"] = 7
        attribute = controller.registers.attributes["current_x_index"]
        await attribute.wait_for_value(7, timeout=2 * INDICATOR_PERIOD)

    serve_controller(backend, body)


def test_a_rejected_board_write_fails_and_reads_back() -> None:
    """Raise the board's refusal to the writer and show the value the board kept."""
    backend = StubBackend({"max_pixel": 3}, write_error=RuntimeError("board said no"))

    async def body(controller: McsController) -> None:
        attribute = controller.registers.attributes["max_pixel"]
        await attribute.update(0)
        with pytest.raises(RuntimeError):
            await attribute.put(9)
        assert attribute.get() == 3

    serve_controller(backend, body)


def test_failing_reads_warn_once_and_recover_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Log one warning when indicator reads start failing and one info line when they recover."""
    monkeypatch.setattr(mcs, "INDICATOR_PERIOD", 0.01)
    backend = StubBackend({"current_x_index": 0}, failing_reads=range(2, 5))

    async def body(controller: McsController) -> None:
        backend.values["current_x_index"] = 7
        await controller.registers.attributes["current_x_index"].wait_for_value(7, timeout=1)

    with caplog.at_level(logging.INFO, logger="brighteyes_mcs"):
        serve_controller(backend, body)

    passes = [record for record in caplog.records if "indicator" in record.getMessage()]
    assert [record.levelno for record in passes] == [logging.WARNING, logging.INFO]


def test_one_bad_value_does_not_stop_the_pass(caplog: pytest.LogCaptureFixture) -> None:
    """Update the other registers and log the register whose value is refused."""
    backend = StubBackend({"current_x_index": 7, "spad_configuration_message": 2**60})

    async def body(controller: McsController) -> None:
        assert controller.registers.attributes["current_x_index"].get() == 7

    with caplog.at_level(logging.ERROR, logger="brighteyes_mcs"):
        serve_controller(backend, body)

    assert any("spad_configuration_message" in record.getMessage() for record in caplog.records)


def test_a_write_after_disconnect_is_ignored() -> None:
    """Accept a register write made after the controller disconnected, as the stop at exit is."""
    backend = DictRegisters(fake_specs(), {})

    async def body(controller: McsController) -> None:
        pass

    serve_controller(backend, body)

    asyncio.run(backend.write_many({"stop_command": True}))


def test_a_whole_number_reaches_the_backend_as_an_integer() -> None:
    """Hand the backend an integer for a register served as a double, as the board needs."""
    backend = StubBackend({})

    async def body(controller: McsController) -> None:
        await controller.registers.attributes["dfd_dwell_time_cycles_120mhz"].put(5.0)

    serve_controller(backend, body)

    assert backend.written == [{"dfd_dwell_time_cycles_120mhz": 5}]
    assert type(backend.written[0]["dfd_dwell_time_cycles_120mhz"]) is int


def test_a_read_back_the_busy_board_skipped_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry the read-back of a written control on a later pass when the board was busy."""
    monkeypatch.setattr(mcs, "INDICATOR_PERIOD", 0.01)
    backend = StubBackend({"max_pixel": 1}, busy_reads=range(2, 3))

    async def body(controller: McsController) -> None:
        backend.values["max_pixel"] = 6
        writer = threading.Thread(target=backend.listeners[0], args=("max_pixel",))
        writer.start()
        writer.join()
        await controller.registers.attributes["max_pixel"].wait_for_value(6, timeout=1)

    serve_controller(backend, body)


def test_a_failed_start_ends_serving_with_its_error() -> None:
    """Raise the error that stopped the controller connecting, instead of waiting forever."""
    controller = McsController(
        fake_specs(), StubBackend({}, failing_reads=range(1, 2)), simulated=True
    )

    with pytest.raises(RuntimeError, match="board did not answer"):
        asyncio.run(asyncio.wait_for(serve(controller, "BETESTSTART"), timeout=10))
