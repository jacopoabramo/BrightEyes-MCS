"""Register values of the BrightEyes FPGA, computed from settings in physical units.

Each class describes one group of settings and returns the registers that
group sets, under their register names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

Triple = tuple[float, float, float]

WAIT_CLOCK_HZ = 40e6


@dataclass(frozen=True)
class ScanArea:
    """Where the scan lies: its size, centre and sampling on the x, y and z axes."""

    range_um: Triple
    offset_um: Triple
    calibration_um_per_volt: Triple
    extra_offset_volts: Triple
    pixels: int
    lines: int
    frames: int
    repetitions: int

    def centre_volts(self, include_extra_offset: bool = False) -> Triple:
        """Return the scan centre in volts, optionally shifted by the extra offset.

        Raises
        ------
        ZeroDivisionError
            When a calibration is zero.
        """
        x, y, z = (
            offset / calibration + (extra if include_extra_offset else 0.0)
            for offset, calibration, extra in zip(
                self.offset_um, self.calibration_um_per_volt, self.extra_offset_volts, strict=True
            )
        )
        return x, y, z

    def registers(self) -> dict[str, Any]:
        """Return the step size, start offset and counts of the scan.

        Raises
        ------
        ZeroDivisionError
            When a calibration is zero.
        """
        centre = self.centre_volts()
        start_offset = [
            centre_volts - (0.5 * range_um / calibration) + extra
            for centre_volts, range_um, calibration, extra in zip(
                centre,
                self.range_um,
                self.calibration_um_per_volt,
                self.extra_offset_volts,
                strict=True,
            )
        ]
        return {
            "axis_calibration_volts_per_step": (
                np.asarray(self.range_um)
                / np.asarray(self.calibration_um_per_volt)
                / np.asarray([self.pixels, self.lines, self.frames])
            ),
            "axis_start_offset_volts": np.asarray(start_offset),
            "max_pixel": self.pixels,
            "max_line": self.lines,
            "max_frame": self.frames,
            "max_repetition": self.repetitions + 1,
        }


@dataclass(frozen=True)
class Timing:
    """How long each part of the scan takes.

    The two waits are counted at a fixed 40 MHz, whatever `clock_base_mhz` is.
    """

    time_resolution_us: float
    timebins_per_pixel: int
    wait_for_laser_s: float
    wait_after_frame_s: float
    wait_first_time_only: bool
    circular_points: int = 1
    circular_repetitions: int = 1
    clock_base_mhz: float = 40.0

    def registers(self) -> dict[str, Any]:
        """Return the cycle counts of the scan, each truncated toward zero."""
        return {
            "time_bin_dwell_cycles": int(self.time_resolution_us * self.clock_base_mhz),
            "max_time_bins_per_pixel": int(self.timebins_per_pixel),
            "tag_clock_duration_cycles": int(
                self.timebins_per_pixel * self.time_resolution_us * self.clock_base_mhz / 2
            ),
            "wait_laser_startup_cycles": int(self.wait_for_laser_s * WAIT_CLOCK_HZ),
            "wait_post_frame_cycles": int(self.wait_after_frame_s * WAIT_CLOCK_HZ),
            "wait_laser_first_time_only_enable": self.wait_first_time_only,
            "max_circular_point": self.circular_points,
            "max_circular_repetition": self.circular_repetitions,
        }
