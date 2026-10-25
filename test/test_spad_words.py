import numpy as np
import numpy.typing as npt
from brighteyes_mcs_cylibs.fastconverter import convertRawDataToCountsDirect

from brighteyes_mcs.acquisition.detectors.pispad23.backend import (
    pispad23_pack_counts_to_spad25_words,
)
from test.acquisition_harness import CHANNEL_MAX


def decode(
    words: npt.NDArray[np.uint64], mask: npt.NDArray[np.uint8] | None = None
) -> tuple[npt.NDArray[np.uint64], npt.NDArray[np.uint64], npt.NDArray[np.uint64]]:
    samples = len(words) // 2
    counts = np.zeros((samples, 27), dtype=np.uint64)
    total = np.zeros(samples, dtype=np.uint64)
    saturation = np.zeros(27, dtype=np.uint64)
    result = convertRawDataToCountsDirect(
        data=words,
        start=0,
        stop=len(words),
        buffer_out=counts,
        buffer_sum=total,
        fingerprint_saturation=saturation,
        mask=np.ones(25, dtype=np.uint8) if mask is None else mask,
    )
    assert result == 0
    return counts, total, saturation


def test_packed_counts_decode_to_the_same_counts() -> None:
    """Decode packed counts within each channel's width to the same counts."""
    rng = np.random.default_rng(0)
    counts = rng.integers(0, CHANNEL_MAX + 1, size=(1000, 25), dtype=np.uint64)

    decoded, total, _ = decode(pispad23_pack_counts_to_spad25_words(counts))

    np.testing.assert_array_equal(decoded[:, :25], counts)
    np.testing.assert_array_equal(decoded[:, 25:], 0)
    np.testing.assert_array_equal(total, counts.sum(axis=1))


def test_counts_above_the_channel_width_are_clipped() -> None:
    """Clip a count to its channel's width and count the sample as saturated."""
    counts = np.zeros((2, 25), dtype=np.uint64)
    counts[0, 0] = 31
    counts[1, 12] = 2000

    decoded, _, saturation = decode(pispad23_pack_counts_to_spad25_words(counts))

    assert decoded[0, 0] == 15
    assert decoded[1, 12] == 1023
    assert saturation[0] == 1
    assert saturation[12] == 1


def test_mask_drops_channels_from_the_sum() -> None:
    """Leave a masked channel out of the sum but keep its decoded count."""
    counts = np.ones((3, 25), dtype=np.uint64)
    mask = np.ones(25, dtype=np.uint8)
    mask[3] = 0

    decoded, total, _ = decode(pispad23_pack_counts_to_spad25_words(counts), mask)

    np.testing.assert_array_equal(total, [24, 24, 24])
    np.testing.assert_array_equal(decoded[:, 3], [1, 1, 1])
