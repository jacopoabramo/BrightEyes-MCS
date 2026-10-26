"""Pin how FIFO packets travel from the reader loops through the preprocessor."""

from collections import namedtuple
from collections.abc import Callable
import inspect
import multiprocessing as mp
import queue
import threading
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from brighteyes_mcs.acquisition.manager import create_i64_counter
from brighteyes_mcs.acquisition.workers.detectors.spad.preprocessor import SpadDataPreProcess
from brighteyes_mcs.acquisition.workers.fpga import NiFpgaControlProcess

ReadValues = namedtuple("ReadValues", ["data", "elements_remaining"])


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Return once `predicate` holds, or fail the test after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("condition not reached")
        time.sleep(0.01)


def control_process(
    *, timeout_fifos: float = 50e6, use_rust_fifo: bool = True
) -> NiFpgaControlProcess:
    """Build the FPGA control process around in-process events and queues."""
    configuration: dict[str, Any] = {
        "timeout_fifos": timeout_fifos,
        "bitfile": "unused.lvbitx",
        "ni_address": "RIO0",
        "requested_fifo_depth": 1000,
        "stop_event": threading.Event(),
        "stop_done_event": threading.Event(),
        "print_event": threading.Event(),
        "queueFifoRead": queue.Queue(),
        "is_connected": threading.Event(),
        "is_readytorun": threading.Event(),
        "initialization_error": {},
        "list_registers": [],
        "actual_fifo_depth": mp.Value("I", 0),
        "fpgarunning": threading.Event(),
        "fpga_started": threading.Event(),
        "list_fifos_to_read_continously": ["stream_out_main"],
        "fifo_chuck_size_digital": mp.Value("I", 2),
        "fifo_chuck_size_analog": mp.Value("I", 4),
        "expected_words_data_digital": mp.Value("q", 0),
        "expected_words_data_analog": mp.Value("q", 0),
        "initial_registers": {},
        "detector_model": "SPAD Array",
    }
    return NiFpgaControlProcess(configuration, debug=False, use_rust_fifo=use_rust_fifo)


def start_thread(target: Callable[..., object], *args: object) -> threading.Thread:
    """Run `target` on a daemon thread and return the started thread."""
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def drain(source: Any) -> list[Any]:
    """Return every item waiting in `source`."""
    items = []
    while not source.empty():
        items.append(source.get_nowait())
    return items


class FakeRustReader:
    """Stand-in for the Rust FIFO reader, returning prepared reads, then empty ones."""

    def __init__(self, reads: list[list[int]]) -> None:
        self.reads = [np.array(read, np.uint64) for read in reads]
        self.calls = 0

    def read_data(self, fifo: str) -> np.ndarray:
        self.calls += 1
        return self.reads.pop(0) if self.reads else np.array([], np.uint64)


class FakeNiFifo:
    """Stand-in for an NI FIFO, returning prepared lists, then empty ones."""

    def __init__(self, reads: list[list[int]]) -> None:
        self.reads = list(reads)
        self.calls = 0

    def read(self, number_of_elements: int, timeout_ms: float) -> ReadValues:
        self.calls += 1
        return ReadValues(self.reads.pop(0) if self.reads else [], 0)


def preprocessor_for(
    incoming: queue.Queue[Any], outgoing: queue.Queue[np.ndarray]
) -> tuple[SpadDataPreProcess, dict[str, Any], dict[str, Any]]:
    """Build a SPAD preprocessor for `stream_out_main` with its two counters."""
    loc_acquired = {"stream_out_main": create_i64_counter()}
    last_len = {"stream_out_main": create_i64_counter()}
    preprocessor = SpadDataPreProcess(
        incoming,
        loc_acquired,
        last_len,
        {"stream_out_main": outgoing},
        {"stream_out_main": np.uint64},
    )
    return preprocessor, loc_acquired, last_len


def test_preprocessor_sends_each_packet_as_one_array_with_its_words_intact() -> None:
    """Convert each packet to one output array, keeping 64-bit words and counters."""
    packets = [np.array([2**53 + 1, 2**64 - 1, 7], np.uint64), np.array([5], np.uint64)]
    incoming: queue.Queue[Any] = queue.Queue()
    for packet in packets:
        incoming.put(("stream_out_main", packet))
    outgoing: queue.Queue[np.ndarray] = queue.Queue()
    preprocessor, loc_acquired, last_len = preprocessor_for(incoming, outgoing)

    thread = start_thread(inspect.unwrap(SpadDataPreProcess.run), preprocessor)
    wait_until(lambda: outgoing.qsize() == len(packets))
    preprocessor.stop_event.set()
    thread.join(2.0)

    outputs = drain(outgoing)
    assert [output.tolist() for output in outputs] == [
        np.fromiter(packet.tolist(), np.uint64).astype(np.uint64).tolist() for packet in packets
    ]
    assert loc_acquired["stream_out_main"].value == 4
    assert last_len["stream_out_main"].value == 1


def test_preprocessor_stops_promptly_with_an_empty_queue() -> None:
    """Finish within a second of the stop event while no packet arrives."""
    preprocessor, _, _ = preprocessor_for(queue.Queue(), queue.Queue())
    thread = start_thread(inspect.unwrap(SpadDataPreProcess.run), preprocessor)

    preprocessor.stop_event.set()

    assert preprocessor.stop_event_done.wait(1.0)
    thread.join(1.0)


def test_rust_loop_puts_each_nonempty_read_as_its_own_tuple() -> None:
    """Put only reads that returned words, each as a (fifo, words) tuple."""
    process = control_process()
    process.rust_fifo_reader = FakeRustReader([[1, 2], [], [3]])
    process.rust_reader_ready.set()
    process.fifo_last_read_time["stream_out_main"] = time.perf_counter_ns()

    thread = start_thread(process.loop_fifo_read_continuously_rust_fifo, "stream_out_main")
    wait_until(lambda: process.queue_fifo_read.qsize() == 2)
    process.stop_event.set()
    thread.join(2.0)

    items = drain(process.queue_fifo_read)
    assert all(type(item) is tuple for item in items)
    assert [(fifo, words.tolist()) for fifo, words in items] == [
        ("stream_out_main", [1, 2]),
        ("stream_out_main", [3]),
    ]


def test_ni_loop_puts_reads_as_uint64_arrays() -> None:
    """Put each NI FIFO read as a (fifo, uint64 array) tuple."""
    process = control_process(use_rust_fifo=False)
    process.nifpga_session = SimpleNamespace(fifos={"stream_out_main": FakeNiFifo([[1, 2]])})
    process.fpgarunning_internal = True
    process.fifo_element_remaining["stream_out_main"] = 0

    thread = start_thread(process.loop_fifo_read_continuously)
    wait_until(lambda: process.queue_fifo_read.qsize() == 1)
    process.stop_event.set()
    thread.join(2.0)

    items = drain(process.queue_fifo_read)
    assert [(fifo, words.dtype, words.tolist()) for fifo, words in items] == [
        ("stream_out_main", np.dtype(np.uint64), [1, 2])
    ]
