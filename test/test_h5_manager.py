import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import h5py
import numpy as np

from brighteyes_mcs.storage.h5 import H5Manager

IMPORT_WITHOUT_QT = """
import sys

for name in ("PySide6", "pyqtgraph", "qtpy"):
    sys.modules[name] = None

import brighteyes_mcs.storage.converters.spad
import brighteyes_mcs.storage.h5
"""


def test_repetitions_grow_the_first_axis(tmp_path: Path) -> None:
    """Grow the dataset to the highest repetition written and leave gaps zero."""
    path = tmp_path / "scan.h5"
    manager = H5Manager(str(path))
    manager.init_dataset("data", [4, 3, 2], 5, 25, np.uint16)
    blocks = {
        (rep, z): np.full((3, 4, 5, 25), 10 * rep + z + 1, dtype=np.uint16)
        for rep in (0, 2)
        for z in (0, 1)
    }
    for (rep, z), block in blocks.items():
        manager.add_to_dataset("data", block, rep, z)
    manager.close()

    with h5py.File(path) as h5file:
        data = h5file["data"][()]
    assert data.shape == (3, 2, 3, 4, 5, 25)
    assert data.dtype == np.uint16
    np.testing.assert_array_equal(data[1], 0)
    for (rep, z), block in blocks.items():
        np.testing.assert_array_equal(data[rep, z], block)


def test_metadata_values_are_converted_for_hdf5(tmp_path: Path) -> None:
    """Store lists as float64 arrays, decimals as floats, dicts as text, and skip None."""
    path = tmp_path / "scan.h5"
    manager = H5Manager(str(path))
    manager.metadata_add_dict(
        "configurationGUI",
        {"offsets": [1, 2], "step": Decimal("1.5"), "nested": {"a": 1}, "unset": None},
    )
    manager.close()

    with h5py.File(path) as h5file:
        attributes = dict(h5file["configurationGUI"].attrs)
    assert set(attributes) == {"offsets", "step", "nested"}
    assert attributes["offsets"].dtype == np.float64
    np.testing.assert_array_equal(attributes["offsets"], [1.0, 2.0])
    assert attributes["step"] == 1.5
    assert attributes["nested"] == "{'a': 1}"


def test_thumbnail_is_stored_as_given(tmp_path: Path) -> None:
    """Store the encoded thumbnail bytes unchanged in the `thumbnail` dataset."""
    path = tmp_path / "scan.h5"
    jpeg = bytes([0xFF, 0xD8, 0x00, 0x7F, 0xFF, 0xD9])
    manager = H5Manager(str(path))
    manager.metadata_add_thumbnail(jpeg)
    manager.close()

    with h5py.File(path) as h5file:
        thumbnail = h5file["thumbnail"]
        assert thumbnail.shape == (1,)
        assert thumbnail[0].tobytes() == jpeg


def test_storage_imports_without_qt() -> None:
    """Import the HDF5 writer and the RAW converter in an interpreter without Qt."""
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_WITHOUT_QT], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
