"""Register values of the BrightEyes FPGA, computed from settings in physical units.

Each class describes one group of settings and returns the registers that
group sets, under their register names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import numpy as np

if TYPE_CHECKING:
    from .settings import AcquisitionConfig

Triple = tuple[float, float, float]

WAIT_CLOCK_HZ = 40e6
CIRCULAR_REGISTER_LENGTH = 32
LASER_SEQUENCE_LENGTH = 24

ANALOG_OUTPUT_SOURCES: Final = (
    "X",
    "Y",
    "Z",
    "Constant",
    "Laser 1",
    "Laser 2",
    "Laser 3",
    "Laser 4",
    "X2",
    "Y2",
    "Z2",
)
"""Sources an analog output can send, at the position of their selector value."""

CONSTANT_SOURCE_SELECTOR: Final = 15
"""Selector value of the "Constant" source, which differs from its position."""


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


def lissajous_offsets(
    radius: float,
    point_count: int,
    omega_x: int = 1,
    omega_y: int = 1,
    phase_deg: float = 0,
    first_position: int = 0,
    open_curve: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a rotated trajectory with the selected point at index zero."""
    point_count = int(point_count)
    if point_count <= 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)

    if open_curve:
        # The odd x frequency gives opposite x coordinates at the two
        # endpoints, while the integer y frequency returns y to zero.
        t = np.linspace(0.0, 1.0, point_count)
        x_unrotated = -np.cos((2 * int(omega_x) + 1) * np.pi * t) * float(radius)
        y_unrotated = np.sin(int(omega_y) * np.pi * t) * float(radius)
    else:
        t = np.linspace(0, 2 * np.pi, point_count + 1)[:-1]
        x_unrotated = np.cos(int(omega_x) * t) * float(radius)
        y_unrotated = np.sin(int(omega_y) * t) * float(radius)
    phase_rad = np.deg2rad(float(phase_deg))
    cos_phase = np.cos(phase_rad)
    sin_phase = np.sin(phase_rad)
    x_values = (
        x_unrotated * cos_phase - y_unrotated * sin_phase,
        x_unrotated * sin_phase + y_unrotated * cos_phase,
    )
    first_index = int(first_position) % point_count
    return (
        np.roll(x_values[0], -first_index),
        np.roll(x_values[1], -first_index),
    )


def circular_points_for_projection(
    registers: Mapping[str, Any],
    projection: str,
    calibration: Sequence[float],
    offset: Sequence[float],
    point_count: int,
    scan_range: Sequence[float] | None = None,
    pixel_counts: Sequence[int] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Add calibrated circular displacements to raster-pixel centers."""
    arrays = []
    for register_name in (
        "circular_scan_x_volts",
        "circular_scan_y_volts",
        "circular_scan_z_volts",
    ):
        try:
            array = np.asarray(registers.get(register_name, []), dtype=float).reshape(-1)
        except (TypeError, ValueError):
            return np.asarray([]), np.asarray([])
        arrays.append(array)

    count = min(
        max(0, int(point_count)),
        *(len(array) for array in arrays),
    )
    if count == 0:
        return np.asarray([]), np.asarray([])

    circular_displacements = [arrays[axis][:count] * float(calibration[axis]) for axis in range(3)]
    axes = {
        "xy": (0, 1),
        "yx": (1, 0),
        "zy": (2, 1),
        "yz": (1, 2),
        "zx": (2, 0),
        "xz": (0, 2),
    }.get(projection, (0, 1))

    if scan_range is None or pixel_counts is None:
        raster_centers = [np.asarray([float(offset[axis])]) for axis in range(3)]
    else:
        raster_centers = []
        for axis in range(3):
            axis_count = max(1, int(pixel_counts[axis]))
            axis_range = float(scan_range[axis])
            pixel_size = axis_range / axis_count
            raster_centers.append(
                float(offset[axis])
                - axis_range / 2.0
                + (np.arange(axis_count, dtype=float) + 0.5) * pixel_size
            )

    projected_center_x, projected_center_y = np.meshgrid(
        raster_centers[axes[0]],
        raster_centers[axes[1]],
        indexing="xy",
    )
    center_x = projected_center_x.reshape(-1, 1)
    center_y = projected_center_y.reshape(-1, 1)
    projected_x = (center_x + circular_displacements[axes[0]].reshape(1, -1)).reshape(-1)
    projected_y = (center_y + circular_displacements[axes[1]].reshape(1, -1)).reshape(-1)
    return projected_x, projected_y


@dataclass(frozen=True)
class ScanPattern:
    """The circular or Lissajous path the scan repeats at each pixel.

    While `lissajous` is false the path is the unit circle, whatever the other
    Lissajous fields hold.
    """

    radius_nm: float
    point_count: int
    calibration_um_per_volt: Triple
    lissajous: bool = False
    omega_x: int = 1
    omega_y: int = 1
    phase_deg: float = 0.0
    first_position: int = 0
    open_curve: bool = False

    def offsets_um(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the x, y and z offsets of the path points in micrometres, z being zero."""
        radius_um = self.radius_nm / 1000.0
        if self.lissajous:
            x, y = lissajous_offsets(
                radius_um,
                self.point_count,
                self.omega_x,
                self.omega_y,
                self.phase_deg,
                self.first_position,
                open_curve=self.open_curve,
            )
        else:
            x, y = lissajous_offsets(radius_um, self.point_count)
        return x, y, np.zeros(self.point_count)

    def volts(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the x, y and z voltages of the path points."""
        x, y, z = (
            offsets / calibration
            for offsets, calibration in zip(
                self.offsets_um(), self.calibration_um_per_volt, strict=True
            )
        )
        return x, y, z

    def registers(self) -> dict[str, Any]:
        """Return the path in volts, each axis padded to 32 points by repeating its last one."""
        return path_registers(self.volts())


@dataclass(frozen=True, eq=False)
class OffsetPattern:
    """A path the scan repeats at each pixel, given as the offsets of its points."""

    offsets_um: tuple[np.ndarray, np.ndarray, np.ndarray]
    calibration_um_per_volt: Triple

    def volts(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return the x, y and z voltages of the path points."""
        x, y, z = (
            np.asarray(offsets, float) / calibration
            for offsets, calibration in zip(
                self.offsets_um, self.calibration_um_per_volt, strict=True
            )
        )
        return x, y, z

    def registers(self) -> dict[str, Any]:
        """Return the path in volts, each axis padded to 32 points by repeating its last one."""
        return path_registers(self.volts())


def path_registers(volts: tuple[np.ndarray, np.ndarray, np.ndarray]) -> dict[str, Any]:
    """Return the circular scan registers of a path in volts, each padded to 32 points.

    An axis shorter than 32 points is padded by repeating its last point.
    """
    registers = {}
    for axis, values in zip("xyz", volts, strict=True):
        if values.shape[0] < CIRCULAR_REGISTER_LENGTH:
            values = np.pad(values, (0, CIRCULAR_REGISTER_LENGTH - values.shape[0]), mode="edge")
        registers[f"circular_scan_{axis}_volts"] = values
    return registers


@dataclass(frozen=True)
class LaserSettings:
    """Which of the four lasers are on, and the order in which they fire."""

    enabled: tuple[bool, bool, bool, bool]
    sequence: tuple[int, ...]

    def enable_registers(self) -> dict[str, Any]:
        """Return the on or off state of each laser."""
        return {f"laser_{number}_enable": on for number, on in enumerate(self.enabled, 1)}

    def sequence_registers(self) -> dict[str, Any]:
        """Return the firing sequence, padded with zeros to 24 steps."""
        sequence = list(self.sequence)
        return {
            "laser_excitation_sequence": sequence + [0] * (LASER_SEQUENCE_LENGTH - len(sequence))
        }


@dataclass(frozen=True)
class ScanOptions:
    """The flags of a run that no other settings group covers.

    Parameters
    ----------
    snake_delay
        The compensation delay the manager applies to snake-walk data; no
        register holds it.
    """

    circular_scan: bool
    dummy_data: bool
    slave_mode: bool
    slave_source: int
    spad_vr0: bool
    spad_vr1: bool
    snake_xy: bool
    snake_z: bool
    dfd_laser_debug: bool
    snake_delay: int

    def registers(self) -> dict[str, Any]:
        """Return the flags under their register names."""
        return {
            "circular_scan_enable": self.circular_scan,
            "dummy_data_enable": self.dummy_data,
            "slave_mode_enable": self.slave_mode,
            "slave_mode_external_source_selector": self.slave_source,
            "spad_vr0_enable": self.spad_vr0,
            "spad_vr1_enable": self.spad_vr1,
            "xy_snake_scan_enable": self.snake_xy,
            "z_snake_scan_enable": self.snake_z,
            "dfd_laser_sync_debug_enable": self.dfd_laser_debug,
            # 5 takes a DFD sample at every point of the circular scan.
            "dfd_trigger_selector": 5,
        }


@dataclass(frozen=True)
class AuxiliaryAxis:
    """One secondary axis (X2, Y2 or Z2), driven through an analog output."""

    position_um: float
    calibration_um_per_volt: float
    extra_offset_volts: float
    minimum_volts: float
    maximum_volts: float

    def volts(self) -> float | None:
        """Return the output voltage of the position, or `None` when the calibration is zero.

        The voltage is clamped between the two limits, in whichever order they
        are given.
        """
        if self.calibration_um_per_volt == 0:
            return None
        voltage = self.position_um / self.calibration_um_per_volt + self.extra_offset_volts
        lower, upper = sorted((self.minimum_volts, self.maximum_volts))
        return min(max(voltage, lower), upper)


@dataclass(frozen=True)
class AnalogOutputs:
    """What each of the eight analog outputs sends.

    A source is a name from `ANALOG_OUTPUT_SOURCES`. An output whose source is
    "Constant" sends its DC voltage.
    """

    sources: tuple[str, ...]
    dc_volts: tuple[float, ...]

    def registers(self) -> dict[str, Any]:
        """Return the source selector and DC voltage of each output."""
        registers: dict[str, Any] = {}
        for channel, (source, volts) in enumerate(zip(self.sources, self.dc_volts, strict=True)):
            registers[f"analog_output_{channel}_source_selector"] = (
                CONSTANT_SOURCE_SELECTOR
                if source == "Constant"
                else ANALOG_OUTPUT_SOURCES.index(source)
            )
            registers[f"analog_output_{channel}_dc_volts"] = volts
        return registers


@dataclass(frozen=True)
class AnalogInputs:
    """How the four analog inputs are conditioned and which ones channels A and B read."""

    integrate: tuple[bool, bool, bool, bool]
    invert: tuple[bool, bool, bool, bool]
    selector_a: int
    selector_b: int
    differential_a: bool
    differential_b: bool

    def registers(self) -> dict[str, Any]:
        """Return the conditioning flags and the input selectors."""
        registers: dict[str, Any] = {}
        for channel, (integrate, invert) in enumerate(
            zip(self.integrate, self.invert, strict=True)
        ):
            registers[f"analog_a_channel_{channel}_integrate_enable"] = integrate
            registers[f"analog_a_channel_{channel}_invert_enable"] = invert
        registers.update(
            {
                "analog_a_input_selector": self.selector_a,
                "analog_b_input_selector": self.selector_b,
                "analog_a_differential_mode_enable": self.differential_a,
                "analog_b_differential_mode_enable": self.differential_b,
            }
        )
        return registers


@dataclass(frozen=True)
class ScanLimits:
    """The voltage range each main scan axis may not leave."""

    minimum_volts: Triple
    maximum_volts: Triple

    def registers(self) -> dict[str, Any]:
        """Return the minimum and maximum voltage of each axis."""
        registers: dict[str, Any] = {}
        for bound, values in (("min", self.minimum_volts), ("max", self.maximum_volts)):
            for axis, value in zip("xyz", values, strict=True):
                registers[f"{bound}_{axis}_volts"] = value
        return registers


@dataclass(frozen=True)
class StreamSelection:
    """Which data streams the FPGA sends during a run."""

    dfd: bool
    analog_fifo: bool
    digital_fifo: bool

    def registers(self) -> dict[str, Any]:
        """Return the DFD and stream enable flags."""
        return {
            "dfd_enable": self.dfd,
            "stream_out_aux_enable": self.analog_fifo,
            "stream_out_main_enable": self.digital_fifo,
        }


def run_registers(config: AcquisitionConfig, *, streams: bool = True) -> list[dict[str, Any]]:
    """Return the register dictionaries that prepare a run, in the order they are written.

    Parameters
    ----------
    streams
        Whether to include the stream enables; a start that only tests the
        scan leaves them as they are.
    """
    writes = []
    if config.options.circular_scan:
        writes.append(config.pattern.registers())
    writes.append(config.timing.registers())
    writes.append({"detector_49_channel_mode_enable": config.detector.channels == 49})
    writes.append(
        {
            **config.timing.registers(),
            **config.scan_area.registers(),
            **config.lasers.enable_registers(),
            **config.lasers.sequence_registers(),
            **config.options.registers(),
        }
    )
    writes.append(config.limits.registers())
    writes.append(config.analog_outputs.registers())
    writes.append(config.analog_inputs.registers())
    if streams:
        writes.append(config.streams.registers())
    return writes
