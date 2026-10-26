"""Pin how the mcs service reads registers from a bitfile and checks written values."""

import logging
from typing import Any

import nifpga
import numpy as np
import pytest
from fastcs.datatypes import Bool, DataType, Int

from brighteyes_mcs.services.registers import (
    ExactWaveform,
    FxpFloat,
    RegisterSpec,
    WholeFloat,
    register_specs,
)
from test.fake_bitfile import fake_bitfile_xml


def fake_specs() -> dict[str, RegisterSpec]:
    """Return the specs of the fake bitfile, by register name."""
    bitfile = nifpga.Bitfile(fake_bitfile_xml(), parse_contents=True)
    return {spec.name: spec for spec in register_specs(bitfile, {})}


@pytest.mark.parametrize(
    ("name", "kind", "served", "writable", "minimum", "maximum"),
    [
        ("start_command", "Bool", Bool, True, None, None),
        ("analog_output_7_source_selector", "U8", Int, True, 0, 255),
        ("max_pixel", "I32", Int, True, -(2**31), 2**31 - 1),
        ("dfd_dwell_time_cycles_120mhz", "U32", WholeFloat, True, 0, 2**32 - 1),
        ("wait_post_frame_cycles", "I64", WholeFloat, True, -(2**53), 2**53),
        ("spad_configuration_message", "U64", WholeFloat, True, 0, 2**53),
        ("current_x_index", "I32", Int, False, -(2**31), 2**31 - 1),
        ("analog_output_0_dc_volts", "Fxp", FxpFloat, True, -16.0, 16.0 - 2**-15),
    ],
)
def test_specs_serve_each_register_type(
    name: str,
    kind: str,
    served: type[DataType[Any]],
    writable: bool,
    minimum: float | None,
    maximum: float | None,
) -> None:
    """Serve each register type with its range and writability."""
    spec = fake_specs()[name]

    assert spec.kind == kind
    assert type(spec.datatype) is served
    assert spec.writable == writable
    if minimum is not None:
        assert spec.datatype.min == minimum
        assert spec.datatype.max == maximum


def test_specs_leave_out_internal_unsupported_and_invalid_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Leave out internal registers, unsupported types and invalid names, warning for the last two."""
    with caplog.at_level(logging.WARNING):
        names = set(fake_specs())

    assert names == {
        "start_command",
        "analog_output_7_source_selector",
        "max_pixel",
        "dfd_dwell_time_cycles_120mhz",
        "wait_post_frame_cycles",
        "spad_configuration_message",
        "current_x_index",
        "analog_output_0_dc_volts",
        "axis_start_offset_volts",
        "digital_outputs",
    }
    warnings = [record.getMessage() for record in caplog.records]
    assert any("error_text" in message for message in warnings)
    assert any("Input U64" in message for message in warnings)
    assert not any("internal_register" in message for message in warnings)


def test_specs_serve_arrays_with_their_length() -> None:
    """Serve an array register as a waveform of its element type and length."""
    specs = fake_specs()
    offsets = specs["axis_start_offset_volts"]
    outputs = specs["digital_outputs"]

    assert offsets.length == 3
    assert isinstance(offsets.datatype, ExactWaveform)
    assert np.dtype(offsets.datatype.array_dtype) == np.float64
    assert offsets.datatype.shape == (3,)
    assert isinstance(outputs.datatype, ExactWaveform)
    assert np.dtype(outputs.datatype.array_dtype) == np.bool_
    assert outputs.datatype.shape == (4,)


def test_fxp_step_comes_from_the_bitfile() -> None:
    """Take a fixed-point register's step from its word lengths in the bitfile."""
    assert fake_specs()["analog_output_0_dc_volts"].datatype.step == 2**-15


def test_out_of_range_integer_is_refused() -> None:
    """Refuse an integer outside the register's type."""
    with pytest.raises(ValueError):
        fake_specs()["analog_output_7_source_selector"].datatype.validate(256)


def test_fractional_value_of_a_whole_register_is_refused() -> None:
    """Refuse a fraction for a register that holds whole numbers."""
    with pytest.raises(ValueError):
        fake_specs()["dfd_dwell_time_cycles_120mhz"].datatype.validate(3.5)


def test_value_past_two_to_the_53_is_refused() -> None:
    """Refuse a value a double cannot hold exactly."""
    with pytest.raises(ValueError):
        fake_specs()["spad_configuration_message"].datatype.validate(2**53 + 1)


def test_fxp_value_is_rounded_to_its_step() -> None:
    """Round a fixed-point value to its step and refuse one out of range."""
    datatype = fake_specs()["analog_output_0_dc_volts"].datatype

    assert datatype.validate(1.00001) == 1.0
    with pytest.raises(ValueError):
        datatype.validate(20.0)


def test_array_of_the_wrong_length_is_refused() -> None:
    """Refuse an array of another length and round each fixed-point element."""
    datatype = fake_specs()["axis_start_offset_volts"].datatype

    with pytest.raises(ValueError):
        datatype.validate([0.0, 0.0])
    assert datatype.validate([0.0, 1.00001, -1.0]).tolist() == [0.0, 1.0, -1.0]
