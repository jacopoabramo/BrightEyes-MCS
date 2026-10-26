"""The board's settings in physical units, and the register values they set.

A setting is named by a dotted path in the service's tree, such as
`scanner.x.range_um`. The register values come from the dataclasses of
`brighteyes_mcs.acquisition.registers`, so a setting writes what the window
writes for the same value.
"""

from __future__ import annotations

import enum
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

import numpy as np

from brighteyes_mcs.acquisition.registers import (
    ANALOG_OUTPUT_SOURCES,
    CIRCULAR_REGISTER_LENGTH,
    CONSTANT_SOURCE_SELECTOR,
    LASER_SEQUENCE_LENGTH,
    AnalogInputs,
    AnalogOutputs,
    AuxiliaryAxis,
    LaserSettings,
    ScanArea,
    ScanLimits,
    ScanOptions,
    WAIT_CLOCK_HZ,
    StreamSelection,
    Timing,
)

Settings = dict[str, Any]

AXES: Final = ("x", "y", "z")
AUX_AXES: Final = ("x2", "y2", "z2")
LASERS: Final = (1, 2, 3, 4)
OUTPUTS: Final = tuple(range(8))
INPUTS: Final = tuple(range(4))

#: Clock the cycle counts of the scan are counted at, in MHz.
CLOCK_MHZ: Final = 40.0

#: Grid setting and register holding the sample count of each main axis.
COUNTS: Final = {"x": "pixels", "y": "lines", "z": "frames"}
COUNT_REGISTERS: Final = {"x": "max_pixel", "y": "max_line", "z": "max_frame"}

#: Registers whose value the run sets, which no setting writes.
RUN_REGISTERS: Final = ("max_repetition", "dfd_trigger_selector")


class Source(enum.Enum):
    """What an analog output sends."""

    X = "X"
    Y = "Y"
    Z = "Z"
    CONSTANT = "Constant"
    LASER_1 = "Laser 1"
    LASER_2 = "Laser 2"
    LASER_3 = "Laser 3"
    LASER_4 = "Laser 4"
    X2 = "X2"
    Y2 = "Y2"
    Z2 = "Z2"


Kind = Literal["bool", "int", "float", "source", "floats", "ints", "text"]


@dataclass(frozen=True)
class Setting:
    """One setting of the tree.

    Parameters
    ----------
    writes
        The registers a put of the setting may write.
    reads
        The other registers its value is computed from.
    held
        Whether the service keeps the value, because no register holds it.
    length
        The element count of an array setting.
    minimum
        The smallest value of an integer setting.
    maximum
        The largest value of an integer setting.
    """

    path: str
    kind: Kind
    writes: frozenset[str]
    reads: frozenset[str] = frozenset()
    held: bool = False
    length: int = 1
    minimum: int | None = None
    maximum: int | None = None
    writable: bool = True

    @property
    def registers(self) -> frozenset[str]:
        """Every register the setting reads or writes."""
        return self.writes | self.reads


def catalogue() -> dict[str, Setting]:
    """Return every setting of the tree under its path."""
    settings: dict[str, Setting] = {}

    def add(path: str, kind: Kind, writes: Collection[str], **options: Any) -> None:
        reads = frozenset(options.pop("reads", ()))
        settings[path] = Setting(path, kind, frozenset(writes), reads, **options)

    step = "axis_calibration_volts_per_step"
    start = "axis_start_offset_volts"
    for axis, count in COUNTS.items():
        add(f"grid.{count}", "int", (COUNT_REGISTERS[axis], step), minimum=1)
    add(
        "grid.time_bins_per_pixel",
        "int",
        ("max_time_bins_per_pixel", "tag_clock_duration_cycles"),
        minimum=1,
    )

    add("pattern.enabled", "bool", ("circular_scan_enable",))
    add(
        "pattern.point_count",
        "int",
        ("max_circular_point",),
        minimum=1,
        maximum=CIRCULAR_REGISTER_LENGTH,
    )
    add("pattern.repetitions", "int", ("max_circular_repetition",), minimum=1)
    for axis in AXES:
        add(
            f"pattern.offsets_{axis}_um",
            "floats",
            (f"circular_scan_{axis}_volts",),
            length=CIRCULAR_REGISTER_LENGTH,
        )
    add("pattern.snake_xy", "bool", ("xy_snake_scan_enable",))
    add("pattern.snake_z", "bool", ("z_snake_scan_enable",))

    for axis in AXES:
        scanner = f"scanner.{axis}"
        add(f"{scanner}.range_um", "float", (step, start), reads=(COUNT_REGISTERS[axis],))
        add(f"{scanner}.offset_um", "float", (start,), reads=(step, COUNT_REGISTERS[axis]))
        add(f"{scanner}.min_volts", "float", (f"min_{axis}_volts",))
        add(f"{scanner}.max_volts", "float", (f"max_{axis}_volts",))
        add(
            f"{scanner}.calibration_um_per_volt",
            "float",
            (step, start, f"circular_scan_{axis}_volts"),
            held=True,
        )
        add(f"{scanner}.extra_offset_volts", "float", (start,), held=True)

    add(
        "timing.time_resolution_us", "float", ("time_bin_dwell_cycles", "tag_clock_duration_cycles")
    )
    add("timing.wait_for_laser_s", "float", ("wait_laser_startup_cycles",))
    add("timing.wait_after_frame_s", "float", ("wait_post_frame_cycles",))
    add("timing.wait_first_time_only", "bool", ("wait_laser_first_time_only_enable",))
    add(
        "timing.laser_sequence",
        "ints",
        ("laser_excitation_sequence",),
        length=LASER_SEQUENCE_LENGTH,
    )

    outputs = [f"analog_output_{channel}_dc_volts" for channel in OUTPUTS]
    selectors = [f"analog_output_{channel}_source_selector" for channel in OUTPUTS]
    for axis in AUX_AXES:
        for name in (
            "position_um",
            "calibration_um_per_volt",
            "extra_offset_volts",
            "min_volts",
            "max_volts",
        ):
            add(f"aux.{axis}.{name}", "float", outputs, reads=selectors, held=True)

    for number in LASERS:
        add(f"lasers.{number}.enabled", "bool", (f"laser_{number}_enable",))

    for channel in OUTPUTS:
        dc = f"analog_output_{channel}_dc_volts"
        add(
            f"analog_out.{channel}.source",
            "source",
            (f"analog_output_{channel}_source_selector", dc),
        )
        add(f"analog_out.{channel}.dc_volts", "float", (dc,))

    for channel in INPUTS:
        add(
            f"analog_in.integrate_{channel}",
            "bool",
            (f"analog_a_channel_{channel}_integrate_enable",),
        )
        add(f"analog_in.invert_{channel}", "bool", (f"analog_a_channel_{channel}_invert_enable",))
    for side in ("a", "b"):
        add(
            f"analog_in.selector_{side}",
            "int",
            (f"analog_{side}_input_selector",),
            minimum=0,
            maximum=255,
        )
        add(f"analog_in.differential_{side}", "bool", (f"analog_{side}_differential_mode_enable",))

    add("detector.model", "text", (), held=True, writable=False)
    add("detector.channels_49", "bool", ("detector_49_channel_mode_enable",))
    add("detector.dummy_data", "bool", ("dummy_data_enable",))
    add("detector.slave_mode", "bool", ("slave_mode_enable",))
    add(
        "detector.slave_source",
        "int",
        ("slave_mode_external_source_selector",),
        minimum=0,
        maximum=255,
    )
    add("detector.spad_vr0", "bool", ("spad_vr0_enable",))
    add("detector.spad_vr1", "bool", ("spad_vr1_enable",))
    add("detector.dfd_laser_debug", "bool", ("dfd_laser_sync_debug_enable",))
    add("detector.dfd", "bool", ("dfd_enable",))
    add("detector.analog_fifo", "bool", ("stream_out_aux_enable",))
    add("detector.digital_fifo", "bool", ("stream_out_main_enable",))
    return settings


SETTINGS: Final = catalogue()


def auxiliary_axis(settings: Settings, axis: str) -> AuxiliaryAxis:
    """Return the auxiliary axis `axis` (`"x2"`, `"y2"` or `"z2"`) as `settings` hold it."""
    return AuxiliaryAxis(
        position_um=settings[f"aux.{axis}.position_um"],
        calibration_um_per_volt=settings[f"aux.{axis}.calibration_um_per_volt"],
        extra_offset_volts=settings[f"aux.{axis}.extra_offset_volts"],
        minimum_volts=settings[f"aux.{axis}.min_volts"],
        maximum_volts=settings[f"aux.{axis}.max_volts"],
    )


def output_volts(settings: Settings, channel: int) -> float:
    """Return the DC voltage of an analog output: its own, or its auxiliary axis's.

    Raises
    ------
    ZeroDivisionError
        When the output sends an auxiliary axis whose calibration is zero.
    """
    source = settings[f"analog_out.{channel}.source"]
    if source.value.lower() not in AUX_AXES:
        return float(settings[f"analog_out.{channel}.dc_volts"])
    volts = auxiliary_axis(settings, source.value.lower()).volts()
    if volts is None:
        raise ZeroDivisionError(f"The calibration of {source.value} is zero")
    return volts


def all_registers(settings: Settings) -> dict[str, Any]:
    """Return every register value the settings set, in the order a run writes them.

    Raises
    ------
    ZeroDivisionError
        When a calibration is zero.
    """

    def triple(name: str) -> tuple[float, float, float]:
        x, y, z = (float(settings[f"scanner.{axis}.{name}"]) for axis in AXES)
        return x, y, z

    calibration = triple("calibration_um_per_volt")
    if 0 in calibration:
        raise ZeroDivisionError("A scanner calibration is zero")
    area = ScanArea(
        range_um=triple("range_um"),
        offset_um=triple("offset_um"),
        calibration_um_per_volt=calibration,
        extra_offset_volts=triple("extra_offset_volts"),
        pixels=settings["grid.pixels"],
        lines=settings["grid.lines"],
        frames=settings["grid.frames"],
        repetitions=0,
    )
    timing = Timing(
        time_resolution_us=settings["timing.time_resolution_us"],
        timebins_per_pixel=settings["grid.time_bins_per_pixel"],
        wait_for_laser_s=settings["timing.wait_for_laser_s"],
        wait_after_frame_s=settings["timing.wait_after_frame_s"],
        wait_first_time_only=settings["timing.wait_first_time_only"],
        circular_points=settings["pattern.point_count"],
        circular_repetitions=settings["pattern.repetitions"],
        clock_base_mhz=CLOCK_MHZ,
    )
    lasers = LaserSettings(
        enabled=(
            settings["lasers.1.enabled"],
            settings["lasers.2.enabled"],
            settings["lasers.3.enabled"],
            settings["lasers.4.enabled"],
        ),
        sequence=tuple(int(step) for step in settings["timing.laser_sequence"]),
    )
    options = ScanOptions(
        circular_scan=settings["pattern.enabled"],
        dummy_data=settings["detector.dummy_data"],
        slave_mode=settings["detector.slave_mode"],
        slave_source=settings["detector.slave_source"],
        spad_vr0=settings["detector.spad_vr0"],
        spad_vr1=settings["detector.spad_vr1"],
        snake_xy=settings["pattern.snake_xy"],
        snake_z=settings["pattern.snake_z"],
        dfd_laser_debug=settings["detector.dfd_laser_debug"],
        snake_delay=0,
    )
    outputs = AnalogOutputs(
        sources=tuple(settings[f"analog_out.{channel}.source"].value for channel in OUTPUTS),
        dc_volts=tuple(output_volts(settings, channel) for channel in OUTPUTS),
    )
    inputs = AnalogInputs(
        integrate=(
            settings["analog_in.integrate_0"],
            settings["analog_in.integrate_1"],
            settings["analog_in.integrate_2"],
            settings["analog_in.integrate_3"],
        ),
        invert=(
            settings["analog_in.invert_0"],
            settings["analog_in.invert_1"],
            settings["analog_in.invert_2"],
            settings["analog_in.invert_3"],
        ),
        selector_a=settings["analog_in.selector_a"],
        selector_b=settings["analog_in.selector_b"],
        differential_a=settings["analog_in.differential_a"],
        differential_b=settings["analog_in.differential_b"],
    )
    limits = ScanLimits(minimum_volts=triple("min_volts"), maximum_volts=triple("max_volts"))
    streams = StreamSelection(
        dfd=settings["detector.dfd"],
        analog_fifo=settings["detector.analog_fifo"],
        digital_fifo=settings["detector.digital_fifo"],
    )

    registers: dict[str, Any] = {
        f"circular_scan_{axis}_volts": np.asarray(settings[f"pattern.offsets_{axis}_um"], float)
        / calibration[index]
        for index, axis in enumerate(AXES)
    }
    registers.update(timing.registers())
    registers["detector_49_channel_mode_enable"] = settings["detector.channels_49"]
    for group in (
        area.registers(),
        lasers.enable_registers(),
        lasers.sequence_registers(),
        options.registers(),
        limits.registers(),
        outputs.registers(),
        inputs.registers(),
        streams.registers(),
    ):
        registers.update(group)
    for name in RUN_REGISTERS:
        del registers[name]
    return registers


def writes(path: str, settings: Settings) -> tuple[str, ...]:
    """Return the registers a put of `path` writes, in the order a run writes them.

    A setting of an auxiliary axis writes the DC voltage of each output that
    sends that axis.
    """
    names: Collection[str] = SETTINGS[path].writes
    if path.startswith("aux."):
        axis = path.split(".")[1]
        names = {
            f"analog_output_{channel}_dc_volts"
            for channel in OUTPUTS
            if settings[f"analog_out.{channel}.source"].value.lower() == axis
        }
    return tuple(name for name in all_registers(settings) if name in names)


def served(register_names: Collection[str]) -> list[str]:
    """Return the paths of the settings whose registers are all in `register_names`."""
    available = frozenset(register_names)
    return [path for path, setting in SETTINGS.items() if setting.registers <= available]


def source_of(selector: int) -> Source:
    """Return the source an analog output's selector value names.

    Raises
    ------
    ValueError
        When the value names no source.
    """
    if selector == CONSTANT_SOURCE_SELECTOR:
        return Source.CONSTANT
    if 0 <= selector < len(ANALOG_OUTPUT_SOURCES):
        return Source(ANALOG_OUTPUT_SOURCES[selector])
    raise ValueError(f"Selector {selector} names no analog output source")


def auxiliary_position(raw: Mapping[str, Any], held: Mapping[str, Any], axis: str) -> float:
    """Return an auxiliary axis's position from the first output sending it, or its held one."""
    for channel in OUTPUTS:
        try:
            source = source_of(raw[f"analog_output_{channel}_source_selector"])
        except ValueError:
            continue
        if source.value.lower() == axis:
            volts = float(raw[f"analog_output_{channel}_dc_volts"])
            extra = held[f"aux.{axis}.extra_offset_volts"]
            return (volts - extra) * held[f"aux.{axis}.calibration_um_per_volt"]
    return float(held[f"aux.{axis}.position_um"])


def derived_value(path: str, raw: Mapping[str, Any], held: Mapping[str, Any]) -> Any:
    """Return the value of the setting `path` computed from the registers and held values.

    Raises
    ------
    KeyError
        When a register or held value it needs is missing.
    ValueError
        When the registers name no valid value, such as an unknown source.
    """
    setting = SETTINGS[path]
    match path.split("."):
        case ["grid", count] if count in COUNTS.values():
            axis = next(axis for axis, name in COUNTS.items() if name == count)
            return int(raw[COUNT_REGISTERS[axis]])
        case ["grid", "time_bins_per_pixel"]:
            return int(raw["max_time_bins_per_pixel"])
        case ["scanner", axis, "range_um"]:
            step = float(raw["axis_calibration_volts_per_step"][AXES.index(axis)])
            calibration = held[f"scanner.{axis}.calibration_um_per_volt"]
            return step * calibration * int(raw[COUNT_REGISTERS[axis]])
        case ["scanner", axis, "offset_um"]:
            start = float(raw["axis_start_offset_volts"][AXES.index(axis)])
            calibration = held[f"scanner.{axis}.calibration_um_per_volt"]
            extra = held[f"scanner.{axis}.extra_offset_volts"]
            range_um = derived_value(f"scanner.{axis}.range_um", raw, held)
            return (start - extra) * calibration + range_um / 2
        case ["pattern", name] if name.startswith("offsets_"):
            axis = name.removeprefix("offsets_").removesuffix("_um")
            volts = np.asarray(raw[f"circular_scan_{axis}_volts"], float)
            return volts * held[f"scanner.{axis}.calibration_um_per_volt"]
        case ["timing", "time_resolution_us"]:
            return int(raw["time_bin_dwell_cycles"]) / CLOCK_MHZ
        case ["timing", "wait_for_laser_s"]:
            return int(raw["wait_laser_startup_cycles"]) / WAIT_CLOCK_HZ
        case ["timing", "wait_after_frame_s"]:
            return int(raw["wait_post_frame_cycles"]) / WAIT_CLOCK_HZ
        case ["timing", "laser_sequence"]:
            return np.asarray(raw["laser_excitation_sequence"], int)
        case ["aux", axis, "position_um"]:
            return auxiliary_position(raw, held, axis)
        case ["analog_out", channel, "source"]:
            return source_of(int(raw[f"analog_output_{channel}_source_selector"]))
    (register,) = setting.writes
    match setting.kind:
        case "bool":
            return bool(raw[register])
        case "int":
            return int(raw[register])
        case _:
            return float(raw[register])


def derive(
    raw: Mapping[str, Any], held: Mapping[str, Any], paths: Collection[str]
) -> tuple[Settings, dict[str, Exception]]:
    """Return the settings of `paths` the registers and held values give, and why others fail.

    Held settings are left out, except the auxiliary positions, which an
    output sending the axis holds.
    """
    derived: Settings = {}
    failures: dict[str, Exception] = {}
    for path in paths:
        if SETTINGS[path].held and not path.endswith(".position_um"):
            continue
        try:
            derived[path] = derived_value(path, raw, held)
        except (ArithmeticError, KeyError, ValueError) as error:
            failures[path] = error
    return derived, failures


def tolerance(path: str, settings: Settings, steps: Mapping[str, float]) -> float:
    """Return the largest difference between a value set and the value read back.

    The difference comes from the resolution of the registers: the step of
    each fixed-point register in `steps`, and one cycle of a cycle count.
    """
    setting = SETTINGS[path]
    if setting.kind not in ("float", "floats"):
        return 0.0
    match path.split("."):
        case ["timing", "time_resolution_us"]:
            return 1 / CLOCK_MHZ
        case ["timing", "wait_for_laser_s" | "wait_after_frame_s"]:
            return 1 / WAIT_CLOCK_HZ
        case ["scanner", axis, "range_um" | "offset_um" as name]:
            calibration = abs(settings[f"scanner.{axis}.calibration_um_per_volt"])
            count = settings[f"grid.{COUNTS[axis]}"]
            if name == "range_um":
                return steps["axis_calibration_volts_per_step"] * calibration * count
            return steps["axis_start_offset_volts"] * calibration * (1 + count / 2)
        case ["pattern", name]:
            axis = name.removeprefix("offsets_").removesuffix("_um")
            calibration = abs(settings[f"scanner.{axis}.calibration_um_per_volt"])
            return steps[f"circular_scan_{axis}_volts"] * calibration
        case ["aux", axis, "position_um"]:
            calibration = abs(settings[f"aux.{axis}.calibration_um_per_volt"])
            return (
                max(steps[f"analog_output_{channel}_dc_volts"] for channel in OUTPUTS) * calibration
            )
    return max((steps.get(register, 0.0) for register in setting.writes), default=0.0)


def defaults() -> Settings:
    """Return a value for every setting, for those the bitfile cannot serve.

    Calibrations default to 1, so that a missing axis does not make the
    register values of the others impossible to compute.
    """
    values: Settings = {}
    for path, setting in SETTINGS.items():
        match setting.kind:
            case "bool":
                values[path] = False
            case "int":
                values[path] = setting.minimum or 0
            case "float":
                values[path] = 1.0 if path.endswith("calibration_um_per_volt") else 0.0
            case "source":
                values[path] = Source.CONSTANT
            case "floats":
                values[path] = np.zeros(setting.length)
            case "ints":
                values[path] = np.zeros(setting.length, dtype=int)
            case "text":
                values[path] = ""
    return values
