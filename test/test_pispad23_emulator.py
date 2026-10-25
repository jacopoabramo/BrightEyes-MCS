import multiprocessing as mp
import socket
import threading

import h5py
import numpy as np
import pytest

from brighteyes_mcs.acquisition.detectors.pispad23.backend import (
    PISPAD23TcpBunchSource,
    pispad23_decode_raw_bunch_to_spad_preview_words,
)
from brighteyes_mcs.acquisition.detectors.pispad23.emulator import (
    make_scene,
    parse_cs,
    run_server,
)
from test.acquisition_harness import CHANNEL_MAX, RunAcquisitionLoop

SCAN_X, SCAN_Y, FRAMES = 6, 4, 2


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.mark.parametrize("line", ["CS,2.0,1,6,4\n", "XS,2.0,1,6,4,0\n"], ids=["fields", "verb"])
def test_parse_cs_rejects_malformed_commands(line: str) -> None:
    """Reject a command with the wrong number of fields or the wrong verb."""
    with pytest.raises(ValueError):
        parse_cs(line)


def test_emulator_frames_reach_the_file(run_acquisition_loop: RunAcquisitionLoop) -> None:
    """Write each emulated frame's scene to its plane, clipped to the channel widths."""
    port = free_port()
    threading.Thread(target=run_server, args=("127.0.0.1", port), daemon=True).start()
    words_per_frame = SCAN_X * SCAN_Y * 2
    source = PISPAD23TcpBunchSource(
        mp.Value("q", words_per_frame),
        mp.Value("q", 0),
        mp.Value("q", words_per_frame * FRAMES),
        mp.Value("q", 0),
        scan_x=SCAN_X,
        scan_y=SCAN_Y,
        scan_frames=FRAMES,
        host="127.0.0.1",
        port=port,
        socket_timeout=10.0,
    )
    source.start()
    packets = []
    while (bunch := source.read_bunch("stream_out_main")) is not None:
        packets.append(pispad23_decode_raw_bunch_to_spad_preview_words(bunch))
    words = np.concatenate(packets)

    run = run_acquisition_loop(
        words, shape=(SCAN_X, SCAN_Y, FRAMES), timebins_per_pixel=1, packets=FRAMES
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        data = h5file["data"][()]
    assert data.shape == (1, FRAMES, SCAN_Y, SCAN_X, 1, 25)
    for z in range(FRAMES):
        scene = make_scene(SCAN_X, SCAN_Y, 23, seed=z).transpose(1, 2, 0).astype(np.uint64)
        np.testing.assert_array_equal(data[0, z, :, :, 0, :23], np.minimum(scene, CHANNEL_MAX[:23]))
        np.testing.assert_array_equal(data[0, z, :, :, 0, 23:], 0)
