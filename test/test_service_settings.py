"""Pin how the mcs service serves its settings in physical units and keeps them in step."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import nifpga
import numpy as np
import pytest

from brighteyes_mcs.services.backends import DictRegisters, RegisterBackend
from brighteyes_mcs.services.mcs import McsController
from brighteyes_mcs.services.physical import SETTINGS, Settings, Source, all_registers
from brighteyes_mcs.services.registers import RegisterSpec, register_specs
from test.fake_bitfile import SETTINGS_REGISTERS, fake_bitfile_xml
from test.test_service_controller import StubBackend
from test.window_settings import settings_of, window_config


def settings_specs() -> list[RegisterSpec]:
    """Return the specs of a fake bitfile holding every register the settings use."""
    return register_specs(
        nifpga.Bitfile(fake_bitfile_xml(SETTINGS_REGISTERS), parse_contents=True), {}
    )


def window_settings() -> Settings:
    """Return the settings of the window configuration."""
    return settings_of(window_config())


def window_registers() -> dict[str, Any]:
    """Return the register values the window configuration sets."""
    return all_registers(window_settings())


def held() -> dict[str, Any]:
    """Return the held settings of the window configuration."""
    return {path: value for path, value in window_settings().items() if SETTINGS[path].held}


class SlowRegisters(DictRegisters):
    """Registers in a dictionary whose writes let other tasks run before they land."""

    async def write_many(self, values: Mapping[str, Any]) -> None:
        await asyncio.sleep(0.01)
        await super().write_many(values)


def serve_settings(
    backend: RegisterBackend, body: Callable[[McsController], Awaitable[None]]
) -> None:
    """Connect a controller serving the settings over `backend`, run `body`, then disconnect."""
    controller = McsController(settings_specs(), backend, simulated=True, held=held())
    controller.post_initialise()

    async def main() -> None:
        await controller.connect()
        try:
            await body(controller)
        finally:
            await controller.disconnect()

    asyncio.run(main())


def setting(controller: McsController, path: str) -> Any:
    """Return the value the controller serves for `path`."""
    return controller.setting_attributes[path].get()


def test_a_put_writes_its_registers_in_one_call() -> None:
    """Write every register of a range put in one backend call."""
    backend = StubBackend(window_registers())

    async def body(controller: McsController) -> None:
        await controller.setting_attributes["scanner.x.range_um"].put(20.0)

    serve_settings(backend, body)

    assert len(backend.written) == 1
    assert backend.written[0].keys() == {
        "axis_calibration_volts_per_step",
        "axis_start_offset_volts",
    }


def test_a_value_a_register_refuses_writes_nothing() -> None:
    """Refuse a range whose step leaves the register's range, before any write."""
    backend = StubBackend(window_registers())

    async def body(controller: McsController) -> None:
        with pytest.raises(ValueError):
            await controller.setting_attributes["scanner.x.range_um"].put(1e6)

    serve_settings(backend, body)

    assert backend.written == []


def test_a_board_refusal_reads_back_and_raises() -> None:
    """Raise the board's error and show the setting the board kept."""
    backend = StubBackend(window_registers(), write_error=RuntimeError("board said no"))

    async def body(controller: McsController) -> None:
        with pytest.raises(RuntimeError):
            await controller.setting_attributes["scanner.x.range_um"].put(20.0)
        assert setting(controller, "scanner.x.range_um") == pytest.approx(40.0, abs=1e-3)

    serve_settings(backend, body)


def test_a_calibration_change_keeps_the_physical_settings() -> None:
    """Keep range, offset and pattern offsets when the x calibration changes."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        before = {
            path: setting(controller, path)
            for path in ("scanner.x.range_um", "scanner.x.offset_um", "pattern.offsets_x_um")
        }

        await controller.setting_attributes["scanner.x.calibration_um_per_volt"].put(10.0)

        assert backend.values["axis_calibration_volts_per_step"][0] == pytest.approx(0.0625)
        assert setting(controller, "scanner.x.range_um") == pytest.approx(
            before["scanner.x.range_um"], abs=1e-3
        )
        assert setting(controller, "scanner.x.offset_um") == pytest.approx(
            before["scanner.x.offset_um"], abs=1e-3
        )
        np.testing.assert_allclose(
            setting(controller, "pattern.offsets_x_um"), before["pattern.offsets_x_um"], atol=1e-3
        )

    serve_settings(backend, body)


def test_a_raw_write_shows_up_in_the_physical_setting() -> None:
    """Show a raw `max_pixel` put as a new pixel count and a new range."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await controller.registers.attributes["max_pixel"].put(128)

        await controller.setting_attributes["grid.pixels"].wait_for_value(128, timeout=0.5)
        assert setting(controller, "scanner.x.range_um") == pytest.approx(80.0, abs=1e-3)

    serve_settings(backend, body)


def test_a_busy_board_keeps_the_written_values_pending() -> None:
    """Show the written values and mark them pending when the read-back finds the board busy."""
    backend = StubBackend(window_registers(), busy_reads=range(2, 10_000))

    async def body(controller: McsController) -> None:
        await controller.setting_attributes["scanner.x.range_um"].put(20.0)

        assert setting(controller, "scanner.x.range_um") == pytest.approx(20.0, abs=1e-3)
        assert {"axis_calibration_volts_per_step", "axis_start_offset_volts"} <= controller.pending

    serve_settings(backend, body)


def test_concurrent_puts_sharing_a_register_end_consistent() -> None:
    """Leave a step matching both a range put and a pixel put sent together."""
    backend = SlowRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await asyncio.gather(
            controller.setting_attributes["scanner.x.range_um"].put(20.0),
            controller.setting_attributes["grid.pixels"].put(128),
        )

    serve_settings(backend, body)

    assert backend.values["axis_calibration_volts_per_step"][0] == pytest.approx(20 / 5 / 128)


def test_an_auxiliary_position_reaches_its_outputs() -> None:
    """Write an X2 position to each output sending X2, and to an output switched to X2."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await controller.setting_attributes["aux.x2.position_um"].put(5.0)
        assert backend.values["analog_output_4_dc_volts"] == pytest.approx(5.0)

        await controller.setting_attributes["analog_out.0.source"].put(Source.X2)
        assert backend.values["analog_output_0_source_selector"] == 8
        assert backend.values["analog_output_0_dc_volts"] == pytest.approx(5.0)

    serve_settings(backend, body)


def test_a_dc_put_on_an_auxiliary_output_is_refused() -> None:
    """Refuse a DC voltage put on an output whose source is an auxiliary axis."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        with pytest.raises(ValueError):
            await controller.setting_attributes["analog_out.4.dc_volts"].put(1.0)
        assert backend.values["analog_output_4_dc_volts"] == pytest.approx(4.0)

    serve_settings(backend, body)


def test_a_derive_failure_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    """Log a setting that cannot be derived once across several refreshes."""
    registers = window_registers()
    registers["analog_output_2_source_selector"] = 12
    backend = DictRegisters(settings_specs(), registers)

    async def body(controller: McsController) -> None:
        await controller.refresh(["analog_output_2_source_selector"])
        await controller.refresh(["analog_output_2_source_selector"])

    with caplog.at_level(logging.WARNING, logger="brighteyes_mcs"):
        serve_settings(backend, body)

    failures = [record for record in caplog.records if "analog_out.2.source" in record.getMessage()]
    assert len(failures) == 1


def test_a_raw_write_to_an_auxiliary_output_moves_its_position() -> None:
    """Show a raw DC write on an output sending X2 as a new X2 position."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await controller.registers.attributes["analog_output_4_dc_volts"].put(2.0)

        await controller.setting_attributes["aux.x2.position_um"].wait_for_value(2.0, timeout=0.5)

    serve_settings(backend, body)


def test_a_clamped_auxiliary_position_reads_back_clamped() -> None:
    """Serve the position the clamped voltage gives, not the one put."""
    backend = DictRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await controller.setting_attributes["aux.x2.position_um"].put(1000.0)

        assert setting(controller, "aux.x2.position_um") == pytest.approx(10.0)

    serve_settings(backend, body)


def test_a_raw_put_and_a_setting_put_sent_together_end_consistent() -> None:
    """Leave a step matching both a raw pixel put and a range put sent together."""
    backend = SlowRegisters(settings_specs(), window_registers())

    async def body(controller: McsController) -> None:
        await asyncio.gather(
            controller.registers.attributes["max_pixel"].put(128),
            controller.setting_attributes["scanner.x.range_um"].put(20.0),
        )

    serve_settings(backend, body)

    assert backend.values["axis_calibration_volts_per_step"][0] == pytest.approx(20 / 5 / 128)


def test_a_put_computing_a_value_that_is_not_finite_writes_nothing() -> None:
    """Refuse a put whose step divides by a pixel count of zero, before any write."""
    registers = window_registers()
    registers["max_pixel"] = 0
    backend = StubBackend(registers)

    async def body(controller: McsController) -> None:
        with pytest.raises(ValueError):
            await controller.setting_attributes["grid.lines"].put(16)

    serve_settings(backend, body)

    assert backend.written == []
