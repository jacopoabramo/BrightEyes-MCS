"""Check the register values computed from physical settings."""

import dataclasses

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import (
    AnalogInputs,
    AnalogOutputs,
    AuxiliaryAxis,
    LaserSettings,
    OffsetPattern,
    ScanArea,
    ScanLimits,
    ScanOptions,
    ScanPattern,
    StreamSelection,
    Timing,
    circular_points_for_projection,
    lissajous_offsets,
)

AREA = ScanArea(
    range_um=(10.0, 8.0, 2.0),
    offset_um=(1.0, -2.0, 0.5),
    calibration_um_per_volt=(5.0, 4.0, 2.0),
    extra_offset_volts=(0.1, -0.2, 0.0),
    pixels=100,
    lines=80,
    frames=4,
    repetitions=3,
)


def test_scan_area_registers() -> None:
    """Convert range and offset to volts per step and start offset, with one extra repetition."""
    registers = AREA.registers()
    np.testing.assert_allclose(registers["axis_calibration_volts_per_step"], [0.02, 0.025, 0.25])
    np.testing.assert_allclose(registers["axis_start_offset_volts"], [-0.7, -1.7, -0.25])
    assert (registers["max_pixel"], registers["max_line"], registers["max_frame"]) == (100, 80, 4)
    assert registers["max_repetition"] == 4


def test_scan_area_centre_volts() -> None:
    """Return the scan centre in volts, with and without the extra offset."""
    np.testing.assert_allclose(AREA.centre_volts(), (0.2, -0.5, 0.25))
    np.testing.assert_allclose(AREA.centre_volts(include_extra_offset=True), (0.3, -0.7, 0.25))


def test_scan_area_zero_calibration_raises() -> None:
    """Raise ZeroDivisionError for a zero calibration, before any register is computed."""
    with pytest.raises(ZeroDivisionError):
        dataclasses.replace(AREA, calibration_um_per_volt=(0.0, 4.0, 2.0)).registers()


def test_timing_registers() -> None:
    """Convert microseconds and seconds into clock cycles at a 40 MHz clock base."""
    registers = Timing(1.0, 81, 0.2, 0.05, True).registers()
    assert registers == {
        "time_bin_dwell_cycles": 40,
        "max_time_bins_per_pixel": 81,
        "tag_clock_duration_cycles": 1620,
        "wait_laser_startup_cycles": 8_000_000,
        "wait_post_frame_cycles": 2_000_000,
        "wait_laser_first_time_only_enable": True,
        "max_circular_point": 1,
        "max_circular_repetition": 1,
    }


def test_timing_truncates_cycle_counts() -> None:
    """Truncate cycle counts toward zero instead of rounding them."""
    assert Timing(0.37, 3, 0.0, 0.0, False).registers()["time_bin_dwell_cycles"] == 14


def test_circular_voltage_points_are_calibrated_offset_and_projected() -> None:
    """Scale circular volts by the calibration, add the offset and pick the projected axes."""
    x_points, y_points = circular_points_for_projection(
        registers={
            "circular_scan_x_volts": [1.0, 2.0, 99.0],
            "circular_scan_y_volts": [3.0, 4.0, 99.0],
            "circular_scan_z_volts": [1.0, 2.0, 99.0],
        },
        projection="xz",
        calibration=(2.0, 3.0, 4.0),
        offset=(10.0, 20.0, 30.0),
        point_count=2,
    )

    np.testing.assert_allclose(x_points, [12.0, 14.0])
    np.testing.assert_allclose(y_points, [34.0, 38.0])


def test_unit_lissajous_frequencies_generate_a_circle() -> None:
    """Draw a circle when both frequencies are 1."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=4,
        omega_x=1,
        omega_y=1,
    )

    np.testing.assert_allclose(x_offsets, [2.0, 0.0, -2.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [0.0, 2.0, 0.0, -2.0], atol=1e-12)


def test_lissajous_frequencies_control_each_axis_independently() -> None:
    """Apply each frequency to its own axis."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=4,
        omega_x=2,
        omega_y=1,
    )

    np.testing.assert_allclose(x_offsets, [2.0, -2.0, 2.0, -2.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [0.0, 2.0, 0.0, -2.0], atol=1e-12)


def test_lissajous_phase_rotates_the_generated_curve() -> None:
    """Rotate the curve by the phase."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=4,
        omega_x=1,
        omega_y=1,
        phase_deg=90,
    )

    np.testing.assert_allclose(x_offsets, [0.0, -2.0, 0.0, 2.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [2.0, 0.0, -2.0, 0.0], atol=1e-12)


def test_lissajous_first_position_rotates_the_output_array() -> None:
    """Start the output arrays at the first position."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=1.0,
        point_count=4,
        omega_x=1,
        omega_y=1,
        first_position=1,
    )

    np.testing.assert_allclose(x_offsets, [0.0, -1.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [1.0, 0.0, -1.0, 0.0], atol=1e-12)


def test_open_lissajous_uses_edge_to_edge_trajectory() -> None:
    """Run an open curve from one edge to the opposite one."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=5,
        omega_x=1,
        omega_y=2,
        open_curve=True,
    )

    t = np.linspace(0.0, 1.0, 5)
    np.testing.assert_allclose(x_offsets, -2.0 * np.cos(3 * np.pi * t), atol=1e-12)
    np.testing.assert_allclose(y_offsets, 2.0 * np.sin(2 * np.pi * t), atol=1e-12)
    np.testing.assert_allclose(x_offsets[[0, -1]], [-2.0, 2.0])
    np.testing.assert_allclose(y_offsets[[0, -1]], [0.0, 0.0], atol=1e-12)


PATTERN = ScanPattern(radius_nm=500.0, point_count=4, calibration_um_per_volt=(5.0, 4.0, 2.0))


def test_pattern_registers_are_volts_padded_to_32() -> None:
    """Convert circle points to volts and pad each axis to 32 entries with its last value."""
    registers = PATTERN.registers()
    assert set(registers) == {
        "circular_scan_x_volts",
        "circular_scan_y_volts",
        "circular_scan_z_volts",
    }
    np.testing.assert_allclose(
        registers["circular_scan_x_volts"], [0.1, 0.0, -0.1] + [0.0] * 29, atol=1e-12
    )
    np.testing.assert_allclose(
        registers["circular_scan_y_volts"], [0.0, 0.125, 0.0] + [-0.125] * 29, atol=1e-12
    )
    np.testing.assert_allclose(registers["circular_scan_z_volts"], [0.0] * 32)


def test_pattern_ignores_lissajous_fields_when_off() -> None:
    """Draw the unit circle whatever the Lissajous fields hold while Lissajous is off."""
    bent = dataclasses.replace(
        PATTERN, omega_x=3, omega_y=2, phase_deg=30.0, first_position=1, open_curve=True
    )
    for a, b in zip(bent.offsets_um(), PATTERN.offsets_um(), strict=True):
        np.testing.assert_allclose(a, b)


def test_pattern_uses_lissajous_fields_when_on() -> None:
    """Pass the Lissajous fields to the trajectory while Lissajous is on."""
    on = dataclasses.replace(PATTERN, lissajous=True, omega_x=2)
    x, _y, _z = on.offsets_um()
    np.testing.assert_allclose(x, [0.5, -0.5, 0.5, -0.5], atol=1e-12)


def test_laser_enable_registers() -> None:
    """Map the four laser check boxes to laser_1_enable to laser_4_enable."""
    lasers = LaserSettings((True, False, True, False), tuple(range(1, 13)))
    assert lasers.enable_registers() == {
        "laser_1_enable": True,
        "laser_2_enable": False,
        "laser_3_enable": True,
        "laser_4_enable": False,
    }


def test_laser_sequence_is_padded_to_24() -> None:
    """Pad the twelve-step laser sequence with zeros to 24 entries."""
    lasers = LaserSettings((False,) * 4, tuple(range(1, 13)))
    assert lasers.sequence_registers() == {
        "laser_excitation_sequence": list(range(1, 13)) + [0] * 12
    }


def test_scan_options_registers() -> None:
    """Write the run flags under their register names, with the DFD trigger fixed at 5."""
    options = ScanOptions(True, False, True, 1, True, False, True, False, True, 0)
    assert options.registers() == {
        "circular_scan_enable": True,
        "dummy_data_enable": False,
        "slave_mode_enable": True,
        "slave_mode_external_source_selector": 1,
        "spad_vr0_enable": True,
        "spad_vr1_enable": False,
        "xy_snake_scan_enable": True,
        "z_snake_scan_enable": False,
        "dfd_laser_sync_debug_enable": True,
        "dfd_trigger_selector": 5,
    }


def test_auxiliary_axis_volts() -> None:
    """Convert a secondary position to volts with its calibration and extra offset."""
    assert AuxiliaryAxis(10.0, 5.0, 0.5, -1.0, 3.0).volts() == pytest.approx(2.5)


def test_auxiliary_axis_clamps_with_limits_in_either_order() -> None:
    """Clamp to the limits even when the minimum is above the maximum."""
    assert AuxiliaryAxis(100.0, 5.0, 0.5, -1.0, 3.0).volts() == 3.0
    assert AuxiliaryAxis(100.0, 5.0, 0.5, 3.0, -1.0).volts() == 3.0


def test_auxiliary_axis_zero_calibration_gives_none() -> None:
    """Return None for a zero calibration instead of raising."""
    assert AuxiliaryAxis(10.0, 0.0, 0.5, -1.0, 3.0).volts() is None


def test_analog_outputs_send_constant_as_15() -> None:
    """Send each source's position in the source list, with Constant sent as 15."""
    sources = ("X", "Y", "Z", "Constant", "Laser 1", "Laser 4", "X2", "Z2")
    registers = AnalogOutputs(sources, tuple(0.5 * n for n in range(8))).registers()
    assert [registers[f"analog_output_{n}_source_selector"] for n in range(8)] == [
        0,
        1,
        2,
        15,
        4,
        7,
        8,
        10,
    ]
    assert registers["analog_output_7_dc_volts"] == 3.5


def test_analog_inputs_registers() -> None:
    """Write the integrate and invert flags per channel, the two selectors and the two differential flags."""
    inputs = AnalogInputs(
        integrate=(True, False, False, True),
        invert=(False, True, False, False),
        selector_a=2,
        selector_b=3,
        differential_a=True,
        differential_b=False,
    )
    assert inputs.registers() == {
        "analog_a_channel_0_integrate_enable": True,
        "analog_a_channel_0_invert_enable": False,
        "analog_a_channel_1_integrate_enable": False,
        "analog_a_channel_1_invert_enable": True,
        "analog_a_channel_2_integrate_enable": False,
        "analog_a_channel_2_invert_enable": False,
        "analog_a_channel_3_integrate_enable": True,
        "analog_a_channel_3_invert_enable": False,
        "analog_a_input_selector": 2,
        "analog_b_input_selector": 3,
        "analog_a_differential_mode_enable": True,
        "analog_b_differential_mode_enable": False,
    }


def test_scan_limits_registers() -> None:
    """Write the minimum and maximum voltage of each main axis."""
    limits = ScanLimits(minimum_volts=(-4.0, -3.0, -2.0), maximum_volts=(4.5, 3.5, 2.5))
    assert limits.registers() == {
        "min_x_volts": -4.0,
        "min_y_volts": -3.0,
        "min_z_volts": -2.0,
        "max_x_volts": 4.5,
        "max_y_volts": 3.5,
        "max_z_volts": 2.5,
    }


def test_stream_selection_registers() -> None:
    """Enable DFD and each output stream as selected."""
    streams = StreamSelection(dfd=True, analog_fifo=True, digital_fifo=False)
    assert streams.registers() == {
        "dfd_enable": True,
        "stream_out_aux_enable": True,
        "stream_out_main_enable": False,
    }


def test_an_offset_pattern_writes_what_the_scan_pattern_writes() -> None:
    """Write the same path registers from a pattern's offsets as from its radius."""
    offsets = OffsetPattern(PATTERN.offsets_um(), PATTERN.calibration_um_per_volt)

    for name, volts in PATTERN.registers().items():
        np.testing.assert_allclose(offsets.registers()[name], volts)
