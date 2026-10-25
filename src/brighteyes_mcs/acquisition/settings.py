"""Typed settings that describe a BrightEyes acquisition run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .registers import (
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


@dataclass(frozen=True)
class DetectorConfig:
    """The detector and the FPGA that reads it."""

    model: str
    channels: int
    address: str
    bitfile: str
    pispad23_host: str
    pispad23_port: int
    pispad23_stream_port: int
    pispad23_batch_size: int


@dataclass(frozen=True)
class OutputConfig:
    """Where the run writes its data, and whether it writes any.

    Parameters
    ----------
    raw_files
        The raw output file of each FIFO, used only when `raw_stream` is on.
    """

    filename: str
    save: bool
    raw_stream: bool
    raw_files: Mapping[str, str]


@dataclass(frozen=True)
class LiveAnalysis:
    """The live trace, correlation and preview computed while the run goes."""

    trace_bin_ms: float
    trace_length_s: float
    correlation_bins: int
    show_preview: bool


@dataclass(frozen=True)
class DfdConfig:
    """The digital frequency domain settings, used while `StreamSelection.dfd` is on."""

    bins: int
    clock_multiplier: int


@dataclass(frozen=True)
class AcquisitionConfig:
    """Every setting a run is prepared from."""

    scan_area: ScanArea
    timing: Timing
    pattern: ScanPattern
    lasers: LaserSettings
    options: ScanOptions
    analog_outputs: AnalogOutputs
    analog_inputs: AnalogInputs
    limits: ScanLimits
    streams: StreamSelection
    detector: DetectorConfig
    output: OutputConfig
    live: LiveAnalysis
    dfd: DfdConfig
