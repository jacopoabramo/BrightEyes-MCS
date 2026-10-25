from pathlib import Path

import h5py
import numpy as np
import numpy.typing as npt
import pytest

from brighteyes_mcs.acquisition.detectors.pispad23.backend import (
    pispad23_pack_counts_to_spad25_words,
)
from brighteyes_mcs.storage.converters.spad import convert_raw_acquisition
from test.acquisition_harness import (
    REPETITIONS,
    TIMEBINS,
    RunAcquisitionLoop,
    X,
    Y,
    Z,
    in_file_order,
    scan_counts,
)


def write_raw_acquisition(
    folder: Path, words: npt.NDArray[np.uint64], *, snake_walk_xy: bool
) -> Path:
    """Write a RAW digital stream and its metadata file; return the metadata path."""
    raw_filename = folder / "acquisition_FIFO.raw"
    words.astype(np.uint64).tofile(raw_filename)
    metadata_filename = folder / "acquisition_only_metadata.h5"
    with h5py.File(metadata_filename, "w") as h5file:
        mcs_cfg = h5file.create_group("configurationSpadFCSmanager")
        mcs_cfg.attrs["#pixels"] = X
        mcs_cfg.attrs["#lines"] = Y
        mcs_cfg.attrs["#frames"] = Z
        mcs_cfg.attrs["#repetition"] = REPETITIONS + 1
        mcs_cfg.attrs["#timebinsPerPixel"] = TIMEBINS
        mcs_cfg.attrs["#circular_rep"] = 1
        mcs_cfg.attrs["#circular_points"] = 1
        mcs_cfg.attrs["Cx"] = 40
        h5file.create_group("configurationFPGA")
        h5file.create_group("configurationGUI").attrs["spad_number_of_channels"] = 25
        raw_cfg = h5file.create_group("rawStreamAcquisition")
        raw_cfg.attrs["digital_raw_file"] = str(raw_filename)
        raw_cfg.attrs["digital_channels"] = 25
        raw_cfg.attrs["digital_words_per_sample"] = 2
        raw_cfg.attrs["snake_walk_xy"] = snake_walk_xy
    return metadata_filename


@pytest.mark.parametrize("snake_walk_xy", [False, True], ids=["raster", "snake"])
def test_converted_raw_file_equals_the_live_file(
    run_acquisition_loop: RunAcquisitionLoop, tmp_path: Path, snake_walk_xy: bool
) -> None:
    """Convert a RAW stream to the same data the live loop writes for it."""
    counts = scan_counts()
    words = pispad23_pack_counts_to_spad25_words(counts)
    live = run_acquisition_loop(
        words,
        shape=(X, Y, Z),
        timebins_per_pixel=TIMEBINS,
        packets=8,
        snake_walk_xy=snake_walk_xy,
    )
    metadata_filename = write_raw_acquisition(tmp_path, words, snake_walk_xy=snake_walk_xy)

    converted_filename = tmp_path / "converted.h5"
    convert_raw_acquisition(metadata_filename, converted_filename)

    with h5py.File(converted_filename) as converted, h5py.File(live.h5_path) as written:
        converted_data = converted["data"][()]
        np.testing.assert_array_equal(converted_data, written["data"][()])
    np.testing.assert_array_equal(
        converted_data, in_file_order(counts, snake_walk_xy=snake_walk_xy)
    )
