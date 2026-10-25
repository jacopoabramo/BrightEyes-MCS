"""Check the register values computed from physical settings."""

import dataclasses

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import ScanArea, Timing

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
