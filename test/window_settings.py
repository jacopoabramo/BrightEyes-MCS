"""A window configuration for the settings tests, and the same settings in the service's form."""

import numpy as np

from brighteyes_mcs.acquisition.registers import (
    CIRCULAR_REGISTER_LENGTH,
    LASER_SEQUENCE_LENGTH,
    AnalogInputs,
    AnalogOutputs,
    LaserSettings,
    ScanArea,
    ScanLimits,
    ScanOptions,
    ScanPattern,
    StreamSelection,
    Timing,
)
from brighteyes_mcs.acquisition.settings import (
    AcquisitionConfig,
    DetectorConfig,
    DfdConfig,
    LiveAnalysis,
    OutputConfig,
)
from brighteyes_mcs.services.physical import AXES, Settings, Source

CALIBRATION = (5.0, 4.0, 2.0)

#: Position of each auxiliary axis, chosen so that its voltage equals the DC
#: voltage the window configuration gives the output sending it.
AUX_POSITIONS = {"x2": 4.0, "y2": 3.0, "z2": 7.0}


def window_config() -> AcquisitionConfig:
    """Return a configuration as the window builds it, with a value in every register group."""
    return AcquisitionConfig(
        scan_area=ScanArea(
            range_um=(40.0, 30.0, 2.0),
            offset_um=(1.0, -2.0, 0.5),
            calibration_um_per_volt=CALIBRATION,
            extra_offset_volts=(0.1, 0.0, -0.2),
            pixels=64,
            lines=32,
            frames=4,
            repetitions=3,
        ),
        timing=Timing(
            time_resolution_us=0.5,
            timebins_per_pixel=10,
            wait_for_laser_s=0.002,
            wait_after_frame_s=0.5,
            wait_first_time_only=True,
            circular_points=8,
            circular_repetitions=2,
        ),
        pattern=ScanPattern(radius_nm=500.0, point_count=8, calibration_um_per_volt=CALIBRATION),
        lasers=LaserSettings(enabled=(True, False, True, False), sequence=(1, 3)),
        options=ScanOptions(
            circular_scan=True,
            dummy_data=False,
            slave_mode=False,
            slave_source=2,
            spad_vr0=False,
            spad_vr1=False,
            snake_xy=True,
            snake_z=False,
            dfd_laser_debug=False,
            snake_delay=0,
        ),
        analog_outputs=AnalogOutputs(
            sources=("X", "Y", "Z", "Constant", "X2", "Laser 1", "Constant", "Z2"),
            dc_volts=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0),
        ),
        analog_inputs=AnalogInputs(
            integrate=(True, False, False, True),
            invert=(False, True, False, False),
            selector_a=1,
            selector_b=2,
            differential_a=False,
            differential_b=True,
        ),
        limits=ScanLimits(minimum_volts=(-10.0, -10.0, -5.0), maximum_volts=(10.0, 10.0, 5.0)),
        streams=StreamSelection(dfd=True, analog_fifo=False, digital_fifo=True),
        detector=DetectorConfig(
            model="SPAD Array",
            channels=49,
            address="RIO0",
            bitfile="bitfile",
            pispad23_host="127.0.0.1",
            pispad23_port=9997,
            pispad23_stream_port=9998,
            pispad23_batch_size=1,
        ),
        output=OutputConfig(filename="data", save=False, raw_stream=False, raw_files={}),
        live=LiveAnalysis(
            trace_bin_ms=1.0, trace_length_s=1.0, correlation_bins=8, show_preview=False
        ),
        dfd=DfdConfig(bins=8, clock_multiplier=1),
    )


def padded(values: np.ndarray, length: int) -> np.ndarray:
    """Return `values` padded to `length` by repeating the last one."""
    return np.pad(values, (0, length - values.shape[0]), mode="edge")


def settings_of(config: AcquisitionConfig) -> Settings:
    """Return the settings of `config` under their paths in the service's tree."""
    area, timing, options = config.scan_area, config.timing, config.options
    settings: Settings = {
        "grid.pixels": area.pixels,
        "grid.lines": area.lines,
        "grid.frames": area.frames,
        "grid.time_bins_per_pixel": timing.timebins_per_pixel,
        "pattern.enabled": options.circular_scan,
        "pattern.point_count": timing.circular_points,
        "pattern.repetitions": timing.circular_repetitions,
        "pattern.snake_xy": options.snake_xy,
        "pattern.snake_z": options.snake_z,
        "timing.time_resolution_us": timing.time_resolution_us,
        "timing.wait_for_laser_s": timing.wait_for_laser_s,
        "timing.wait_after_frame_s": timing.wait_after_frame_s,
        "timing.wait_first_time_only": timing.wait_first_time_only,
        "timing.laser_sequence": np.asarray(
            list(config.lasers.sequence)
            + [0] * (LASER_SEQUENCE_LENGTH - len(config.lasers.sequence))
        ),
        "analog_in.selector_a": config.analog_inputs.selector_a,
        "analog_in.selector_b": config.analog_inputs.selector_b,
        "analog_in.differential_a": config.analog_inputs.differential_a,
        "analog_in.differential_b": config.analog_inputs.differential_b,
        "detector.model": config.detector.model,
        "detector.channels_49": config.detector.channels == 49,
        "detector.dummy_data": options.dummy_data,
        "detector.slave_mode": options.slave_mode,
        "detector.slave_source": options.slave_source,
        "detector.spad_vr0": options.spad_vr0,
        "detector.spad_vr1": options.spad_vr1,
        "detector.dfd_laser_debug": options.dfd_laser_debug,
        "detector.dfd": config.streams.dfd,
        "detector.analog_fifo": config.streams.analog_fifo,
        "detector.digital_fifo": config.streams.digital_fifo,
    }
    for index, axis in enumerate(AXES):
        settings[f"scanner.{axis}.range_um"] = area.range_um[index]
        settings[f"scanner.{axis}.offset_um"] = area.offset_um[index]
        settings[f"scanner.{axis}.calibration_um_per_volt"] = area.calibration_um_per_volt[index]
        settings[f"scanner.{axis}.extra_offset_volts"] = area.extra_offset_volts[index]
        settings[f"scanner.{axis}.min_volts"] = config.limits.minimum_volts[index]
        settings[f"scanner.{axis}.max_volts"] = config.limits.maximum_volts[index]
    assert isinstance(config.pattern, ScanPattern)
    for axis, offsets in zip(AXES, config.pattern.offsets_um(), strict=True):
        settings[f"pattern.offsets_{axis}_um"] = padded(offsets, CIRCULAR_REGISTER_LENGTH)
    for axis, position in AUX_POSITIONS.items():
        settings[f"aux.{axis}.position_um"] = position
        settings[f"aux.{axis}.calibration_um_per_volt"] = 1.0
        settings[f"aux.{axis}.extra_offset_volts"] = 0.0
        settings[f"aux.{axis}.min_volts"] = -10.0
        settings[f"aux.{axis}.max_volts"] = 10.0
    for number, enabled in enumerate(config.lasers.enabled, 1):
        settings[f"lasers.{number}.enabled"] = enabled
    outputs = config.analog_outputs
    for channel, (source, volts) in enumerate(zip(outputs.sources, outputs.dc_volts, strict=True)):
        settings[f"analog_out.{channel}.source"] = Source(source)
        settings[f"analog_out.{channel}.dc_volts"] = volts
    inputs = config.analog_inputs
    for channel, (integrate, invert) in enumerate(
        zip(inputs.integrate, inputs.invert, strict=True)
    ):
        settings[f"analog_in.integrate_{channel}"] = integrate
        settings[f"analog_in.invert_{channel}"] = invert
    return settings
