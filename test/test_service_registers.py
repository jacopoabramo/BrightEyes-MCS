"""Pin how the mcs service reads registers from a bitfile and checks written values."""

import logging
from typing import Any

import nifpga
import numpy as np
import pytest
from fastcs.datatypes import Bool, DataType, Int

from brighteyes_mcs.services.registers import (
    NO_DESCRIPTION,
    ExactWaveform,
    FxpFloat,
    RegisterSpec,
    WholeFloat,
    load_descriptions,
    read_descriptions,
    register_specs,
)
from test.fake_bitfile import fake_bitfile_xml

TABLE = """\
| Name | Type | Read/Write | Description |
|------|------|------------|-------------|
| **Main** | | | |
| start_command | Bool | RW | Start the scanning |
| max_pixel | I32 | RW | Number of pixel (X) |
"""


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


def test_descriptions_parse_rows_and_skip_sections() -> None:
    """Read the description of each register row, skipping the header and section rows."""
    assert read_descriptions(TABLE) == {
        "start_command": "Start the scanning",
        "max_pixel": "Number of pixel (X)",
    }


def test_registers_without_a_row_get_no_description() -> None:
    """Describe a register from its row, and one without a row as having no description."""
    bitfile = nifpga.Bitfile(fake_bitfile_xml(), parse_contents=True)
    specs = {spec.name: spec for spec in register_specs(bitfile, read_descriptions(TABLE))}

    assert specs["max_pixel"].description == "Number of pixel (X)"
    assert specs["current_x_index"].description == NO_DESCRIPTION


def test_packaged_table_describes_the_main_registers() -> None:
    """Read the descriptions from the table packaged with the service."""
    assert load_descriptions()["start_command"] == "Start the scanning"


def test_channel_rows_describe_every_channel() -> None:
    """Describe channels 0 to 7 from a channel 7 row under the all-channels note."""
    table = (
        "| **Analog Output** | | | |\n"
        "| (for all channels from 0 to 7) | | | |\n"
        "| analog_output_7_volts | Fxp | RW | Output voltage |\n"
        "| **Main** | | | |\n"
        "| laser_7_enable | Bool | RW | Laser 7 |\n"
    )

    descriptions = read_descriptions(table)

    assert descriptions["analog_output_0_volts"] == "Output voltage"
    assert descriptions["analog_output_7_volts"] == "Output voltage"
    assert "laser_0_enable" not in descriptions
