"""Check the register values computed from physical settings."""

import dataclasses

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import (
    ScanArea,
    ScanPattern,
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


def test_scan_area_registers():
    """Convert range and offset to volts per step and start offset, with one extra repetition."""
    registers = AREA.registers()
    np.testing.assert_allclose(registers["axis_calibration_volts_per_step"], [0.02, 0.025, 0.25])
    np.testing.assert_allclose(registers["axis_start_offset_volts"], [-0.7, -1.7, -0.25])
    assert (registers["max_pixel"], registers["max_line"], registers["max_frame"]) == (100, 80, 4)
    assert registers["max_repetition"] == 4


def test_scan_area_centre_volts():
    """Return the scan centre in volts, with and without the extra offset."""
    np.testing.assert_allclose(AREA.centre_volts(), (0.2, -0.5, 0.25))
    np.testing.assert_allclose(AREA.centre_volts(include_extra_offset=True), (0.3, -0.7, 0.25))


def test_scan_area_zero_calibration_raises():
    """Raise ZeroDivisionError for a zero calibration, before any register is computed."""
    with pytest.raises(ZeroDivisionError):
        dataclasses.replace(AREA, calibration_um_per_volt=(0.0, 4.0, 2.0)).registers()


def test_timing_registers():
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


def test_timing_truncates_cycle_counts():
    """Truncate cycle counts toward zero instead of rounding them."""
    assert Timing(0.37, 3, 0.0, 0.0, False).registers()["time_bin_dwell_cycles"] == 14


def test_circular_voltage_points_are_calibrated_offset_and_projected():
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


def test_unit_lissajous_frequencies_generate_a_circle():
    """Draw a circle when both frequencies are 1."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=4,
        omega_x=1,
        omega_y=1,
    )

    np.testing.assert_allclose(x_offsets, [2.0, 0.0, -2.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [0.0, 2.0, 0.0, -2.0], atol=1e-12)


def test_lissajous_frequencies_control_each_axis_independently():
    """Apply each frequency to its own axis."""
    x_offsets, y_offsets = lissajous_offsets(
        radius=2.0,
        point_count=4,
        omega_x=2,
        omega_y=1,
    )

    np.testing.assert_allclose(x_offsets, [2.0, -2.0, 2.0, -2.0], atol=1e-12)
    np.testing.assert_allclose(y_offsets, [0.0, 2.0, 0.0, -2.0], atol=1e-12)


def test_lissajous_phase_rotates_the_generated_curve():
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


def test_lissajous_first_position_rotates_the_output_array():
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


def test_open_lissajous_uses_edge_to_edge_trajectory():
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


def test_pattern_registers_are_volts_padded_to_32():
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


def test_pattern_ignores_lissajous_fields_when_off():
    """Draw the unit circle whatever the Lissajous fields hold while Lissajous is off."""
    bent = dataclasses.replace(
        PATTERN, omega_x=3, omega_y=2, phase_deg=30.0, first_position=1, open_curve=True
    )
    for a, b in zip(bent.offsets_um(), PATTERN.offsets_um(), strict=True):
        np.testing.assert_allclose(a, b)


def test_pattern_uses_lissajous_fields_when_on():
    """Pass the Lissajous fields to the trajectory while Lissajous is on."""
    on = dataclasses.replace(PATTERN, lissajous=True, omega_x=2)
    x, _y, _z = on.offsets_um()
    np.testing.assert_allclose(x, [0.5, -0.5, 0.5, -0.5], atol=1e-12)
