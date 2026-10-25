import h5py
import numpy as np
import numpy.typing as npt
import pytest
from brighteyes_mcs_cylibs.autocorrelator import Autocorrelator
from brighteyes_mcs_cylibs.timeBinner import timeBinner

from test.acquisition_harness import (
    AUTOCORRELATION_MAXX,
    TIME_RESOLUTION,
    TRACE_BINS,
    TRACE_SAMPLES_PER_BIN,
    RunAcquisitionLoop,
)
from brighteyes_mcs.acquisition.detectors.pispad23.backend import (
    pispad23_pack_counts_to_spad25_words,
)

X, Y, Z, REPETITIONS, TIMEBINS = 4, 3, 2, 2, 4
SAMPLES = X * Y * Z * REPETITIONS * TIMEBINS


def scan_counts() -> npt.NDArray[np.uint64]:
    """Return per-sample counts of 25 channels in acquisition order."""
    index = np.arange(SAMPLES)
    return np.stack([(index + channel) % 3 for channel in range(25)], axis=1).astype(np.uint64)


def in_file_order(
    counts: npt.NDArray[np.uint64], *, snake_walk_xy: bool = False, snake_walk_z: bool = False
) -> npt.NDArray[np.uint64]:
    """Arrange acquisition-order samples as (rep, z, y, x, bin, channel)."""
    ordered = counts.reshape(REPETITIONS, Z, Y, X, TIMEBINS, -1).copy()
    if snake_walk_xy:
        ordered[:, :, 1::2] = ordered[:, :, 1::2, ::-1]
    if snake_walk_z:
        ordered[1::2] = ordered[1::2, ::-1]
    return ordered


def test_frames_reach_the_file_in_scan_order(run_acquisition_loop: RunAcquisitionLoop) -> None:
    """Write every frame of a raster scan to the file at its repetition and plane."""
    counts = scan_counts()

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(counts),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=8,
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        data = h5file["data"][()]
        extra = h5file["data_channels_extra"][()]
    assert data.dtype == np.uint16
    np.testing.assert_array_equal(data, in_file_order(counts))
    assert extra.shape == (REPETITIONS, Z, Y, X, TIMEBINS, 2)
    np.testing.assert_array_equal(extra, 0)


@pytest.mark.parametrize(
    ("snake_walk_xy", "snake_walk_z"), [(True, False), (False, True)], ids=["xy", "z"]
)
def test_snake_scans_reverse_lines_and_planes(
    run_acquisition_loop: RunAcquisitionLoop, snake_walk_xy: bool, snake_walk_z: bool
) -> None:
    """Reverse odd lines for a snake in xy and odd repetitions' planes for a snake in z."""
    counts = scan_counts()

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(counts),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=4,
        snake_walk_xy=snake_walk_xy,
        snake_walk_z=snake_walk_z,
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        data = h5file["data"][()]
    expected = in_file_order(counts, snake_walk_xy=snake_walk_xy, snake_walk_z=snake_walk_z)
    np.testing.assert_array_equal(data, expected)


def test_dfd_folds_time_bins_by_clk_multiplier(run_acquisition_loop: RunAcquisitionLoop) -> None:
    """Fold bins b and b + 2 together and trace the last packet per folded bin."""
    counts = scan_counts()
    packets = 8

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(counts),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=packets,
        dfd_enable=True,
        clk_multiplier=2,
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        data = h5file["data"][()]
    ordered = in_file_order(counts)
    np.testing.assert_array_equal(data, ordered[..., :2, :] + ordered[..., 2:, :])
    last_packet = counts.sum(axis=1)[-SAMPLES // packets :]
    folded_bins = np.arange(SAMPLES)[-SAMPLES // packets :] % 2
    trace_dfd = run.previews["shared_trace_dfd"]
    np.testing.assert_array_equal(trace_dfd[0], [0, 1])
    np.testing.assert_array_equal(
        trace_dfd[1], [last_packet[folded_bins == 0].sum(), last_packet[folded_bins == 1].sum()]
    )
    np.testing.assert_array_equal(trace_dfd[2], [0, 0])


def test_preview_products_follow_the_counts(run_acquisition_loop: RunAcquisitionLoop) -> None:
    """Show the last frame in the images and feed the per-sample sum to trace and FCS."""
    counts = scan_counts()
    per_sample = counts.sum(axis=1)

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(counts),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=8,
    )

    assert run.finished
    last_repetition = in_file_order(counts)[-1].sum(axis=(-1, -2))
    previews = run.previews
    np.testing.assert_array_equal(previews["shared_image_xy"], last_repetition[-1])
    np.testing.assert_array_equal(previews["shared_image_xz"], last_repetition[:, Y // 2, :])
    np.testing.assert_array_equal(previews["shared_image_zy"], last_repetition[:, :, X // 2].T)
    last_frame_channels = counts.reshape(REPETITIONS * Z, -1, 25)[-1].sum(axis=0)
    np.testing.assert_array_equal(previews["shared_fingerprint"][3], last_frame_channels.reshape(5, 5))

    binner = timeBinner(bins=TRACE_BINS, sample_per_bins=TRACE_SAMPLES_PER_BIN)
    binner.add(per_sample)
    np.testing.assert_array_equal(previews["shared_trace"][1], binner.get_bins())
    assert run.trace_pos == binner.get_current_position_bins()

    correlator = Autocorrelator(maxx=AUTOCORRELATION_MAXX, log_step=2)
    correlator.add(per_sample)
    np.testing.assert_allclose(
        previews["shared_autocorrelation"][0], correlator.get_delays() * TIME_RESOLUTION
    )
    np.testing.assert_allclose(
        previews["shared_autocorrelation"][1], correlator.get_correlation_normalized()
    )


def test_analog_samples_reach_the_file(run_acquisition_loop: RunAcquisitionLoop) -> None:
    """Write the low 32 bits of each analog word as channel 0 and the high 32 bits as 1."""
    index = np.arange(SAMPLES, dtype=np.int64)
    high, low = 1000 + index, 5000 + 2 * index
    analog_words = (high.astype(np.uint64) << np.uint64(32)) | low.astype(np.uint64)

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(scan_counts()),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=8,
        analog_words=analog_words,
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        data_analog = h5file["data_analog"][()]
    assert data_analog.dtype == np.int32
    expected = np.stack([low, high], axis=1).astype(np.uint64)
    np.testing.assert_array_equal(data_analog, in_file_order(expected))


@pytest.mark.xfail(
    strict=True,
    reason="the tail of a packet that crosses a frame boundary waits for another packet, "
    "so the last frames are never written",
)
def test_packet_ending_past_a_frame_still_finishes(
    run_acquisition_loop: RunAcquisitionLoop,
) -> None:
    """Finish the scan when the last packet ends past a frame boundary."""
    counts = scan_counts()

    run = run_acquisition_loop(
        pispad23_pack_counts_to_spad25_words(counts),
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=2,
        timeout=3.0,
    )

    assert run.finished
    with h5py.File(run.h5_path) as h5file:
        np.testing.assert_array_equal(h5file["data"][()], in_file_order(counts))
