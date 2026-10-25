"""Run the acquisition loop in-process on synthetic FIFO words.

The loop and the HDF5 writer each run in a thread of the test process and talk
through plain queues, so a test drives decoding, frame split, the preview
products and the HDF5 file without starting processes or touching hardware.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from unittest.mock import patch

import numpy as np
import numpy.typing as npt

from brighteyes_mcs.acquisition.shared_memory import SharedMemoryRegistry
from brighteyes_mcs.acquisition.workers import acquisition_loop
from brighteyes_mcs.acquisition.workers.acquisition_loop import BaseAcquisitionLoopProcess
from brighteyes_mcs.storage.h5 import H5ManagerProcess

AUTOCORRELATION_MAXX = 16
TRACE_BINS = 50
TRACE_SAMPLES_PER_BIN = 4
TIME_RESOLUTION = 1e-6


@dataclass(frozen=True)
class LoopRun:
    """What one in-process run of the acquisition loop left behind."""

    finished: bool
    h5_path: Path
    previews: dict[str, npt.NDArray[Any]]
    trace_pos: int


class RunAcquisitionLoop(Protocol):
    def __call__(
        self,
        digital_words: npt.NDArray[np.uint64],
        *,
        shape: tuple[int, int, int],
        timebins_per_pixel: int,
        packets: int,
        analog_words: npt.NDArray[np.uint64] | None = None,
        snake_walk_xy: bool = False,
        snake_walk_z: bool = False,
        dfd_enable: bool = False,
        clk_multiplier: int = 1,
        timeout: float = 10.0,
    ) -> LoopRun: ...


def run_acquisition_loop(
    directory: Path,
    digital_words: npt.NDArray[np.uint64],
    *,
    shape: tuple[int, int, int],
    timebins_per_pixel: int,
    packets: int,
    analog_words: npt.NDArray[np.uint64] | None = None,
    snake_walk_xy: bool = False,
    snake_walk_z: bool = False,
    dfd_enable: bool = False,
    clk_multiplier: int = 1,
    timeout: float = 10.0,
) -> LoopRun:
    """Feed 25-channel words, split into equal packets, through one acquisition.

    `analog_words`, one word per sample, enables the analog FIFO and is split
    into the same number of packets.
    """
    x, y, z = shape
    dfd_bins = timebins_per_pixel // clk_multiplier
    previews = SharedMemoryRegistry().allocate_preview(
        dim_x=x,
        dim_y=y,
        dim_z=z,
        detector_dim=5,
        autocorrelation_maxx=AUTOCORRELATION_MAXX,
        trace_bins=TRACE_BINS,
        dfd_bins=dfd_bins,
    )
    fifos = ["stream_out_main"] if analog_words is None else ["stream_out_main", "stream_out_aux"]
    command_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    response_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    trace_pos = mp.Value("i", 0)
    shared_objects: dict[str, Any] = {
        **previews,
        "activated_fifos_list": fifos,
        "loc_acquired": {name: mp.Value("q") for name in ("stream_out_main", "stream_out_aux")},
        "loc_previewed": {name: mp.Value("q") for name in ("stream_out_main", "stream_out_aux")},
        "number_of_threads_h5": mp.Value("i", 0),
        "autocorrelation_maxx": AUTOCORRELATION_MAXX,
        "trace_bins": TRACE_BINS,
        "trace_sample_per_bins": TRACE_SAMPLES_PER_BIN,
        "trace_pos": trace_pos,
        "compensation_delay_for_snake": mp.Value("i", 0),
        "h5_command_queue": command_queue,
        "h5_response_queue": response_queue,
    }
    h5_path = directory / "acquisition.h5"
    samples_per_frame = x * y * timebins_per_pixel
    shared_dict: dict[str, Any] = {
        "shape": [x, y, z],
        "spad_channels": 25,
        "timebins_per_pixel": timebins_per_pixel,
        "circ_repetition": 1,
        "circ_points": 1,
        "time_resolution": TIME_RESOLUTION,
        "expected_words_data_digital": len(digital_words),
        "expected_words_data_analog": 0 if analog_words is None else len(analog_words),
        "expected_words_data_per_frame_digital": samples_per_frame * 2,
        "expected_words_data_per_frame_analog": samples_per_frame,
        "filenameh5": str(h5_path),
        "DFD_nbins": dfd_bins,
        "dfd_cycle_mhz": 40,
        "activate_show_preview": True,
        "activate_autocorrelation": True,
        "activate_trace": True,
        "channel": "Sum",
        "preview_buffer_capacity_samples": 100,
        "last_packet_size": 0,
        "dfd_enable": dfd_enable,
        "dfd_peak_idx": -1,
        "snake_walk_xy": snake_walk_xy,
        "snake_walk_z": snake_walk_z,
        "clk_multiplier": clk_multiplier,
        "dfd_shift": 0,
        "current_z_digital": 0,
        "current_rep_digital": 0,
        "current_z_analog": 0,
        "current_rep_analog": 0,
        "total_photon": 0,
    }
    data_queue: dict[str, queue.Queue[npt.NDArray[np.uint64]]] = {
        "stream_out_main": queue.Queue(),
        "stream_out_aux": queue.Queue(),
    }
    for packet in np.array_split(digital_words, packets):
        data_queue["stream_out_main"].put(packet)
    if analog_words is not None:
        for packet in np.array_split(analog_words, packets):
            data_queue["stream_out_aux"].put(packet)

    writer = threading.Thread(
        target=H5ManagerProcess(command_queue, response_queue).run, daemon=True
    )
    writer.start()
    loop = BaseAcquisitionLoopProcess(
        25, shared_objects, False, data_queue, mp.Event(), mp.Event(), shared_dict
    )
    # run() raises the priority of its process, which here is the test process
    with patch.object(acquisition_loop.psutil, "Process"):
        worker = threading.Thread(target=loop.run, daemon=True)
        worker.start()
        worker.join(timeout)
        finished = not worker.is_alive()
        if not finished:
            loop.stop()
            worker.join(timeout)
    writer.join(timeout)
    return LoopRun(
        finished=finished,
        h5_path=h5_path,
        previews={name: array.get_numpy_handle().copy() for name, array in previews.items()},
        trace_pos=trace_pos.value,
    )
