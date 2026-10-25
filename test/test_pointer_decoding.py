import numpy as np
import numpy.typing as npt

from brighteyes_mcs.acquisition.workers.acquisition_loop import decode_pointer_list

SHAPE = (3, 3, 2)
TIMEBINS = 2
SAMPLES = 54

RASTER_X = [0, 1, 2] * 9
RASTER_Y = [0, 0, 0, 1, 1, 1, 2, 2, 2] * 3
RASTER_Z = [0] * 9 + [1] * 9 + [0] * 9
RASTER_REP = [0] * 18 + [1] * 9


def per_sample(per_pixel: list[int]) -> npt.NDArray[np.int64]:
    return np.repeat(np.array(per_pixel, dtype=np.int64), TIMEBINS)


def test_raster_order_without_snake() -> None:
    """Run x fastest, then y, then z, then the repetition."""
    b, x, y, z, rep = decode_pointer_list(0, SAMPLES, TIMEBINS, SHAPE)

    np.testing.assert_array_equal(b, [0, 1] * 27)
    np.testing.assert_array_equal(x, per_sample(RASTER_X))
    np.testing.assert_array_equal(y, per_sample(RASTER_Y))
    np.testing.assert_array_equal(z, per_sample(RASTER_Z))
    np.testing.assert_array_equal(rep, per_sample(RASTER_REP))


def test_snake_xy_reverses_odd_lines() -> None:
    """Reverse x on odd lines only, so the last of three lines runs forward."""
    _, x, y, _, _ = decode_pointer_list(0, SAMPLES, TIMEBINS, SHAPE, snake_walk_xy=True)

    np.testing.assert_array_equal(x, per_sample([0, 1, 2, 2, 1, 0, 0, 1, 2] * 3))
    np.testing.assert_array_equal(y, per_sample(RASTER_Y))


def test_snake_z_reverses_planes_on_odd_repetitions() -> None:
    """Visit the planes in reverse order on odd repetitions."""
    _, _, _, z, rep = decode_pointer_list(0, SAMPLES, TIMEBINS, SHAPE, snake_walk_z=True)

    np.testing.assert_array_equal(z, per_sample([0] * 9 + [1] * 9 + [1] * 9))
    np.testing.assert_array_equal(rep, per_sample(RASTER_REP))


def test_clk_multiplier_folds_time_bins() -> None:
    """Fold the time bins of a pixel by the clock multiplier."""
    b, x, _, _, _ = decode_pointer_list(0, 8, 4, SHAPE, clk_multiplier=2)

    np.testing.assert_array_equal(b, [0, 1, 0, 1, 0, 1, 0, 1])
    np.testing.assert_array_equal(x, [0, 0, 0, 0, 1, 1, 1, 1])


def test_delay_shifts_by_whole_pixels() -> None:
    """Shift every sample forward by the delay, counted in pixels."""
    b, x, y, _, _ = decode_pointer_list(0, 4, TIMEBINS, SHAPE, delay=1)

    np.testing.assert_array_equal(b, [0, 1, 0, 1])
    np.testing.assert_array_equal(x, [1, 1, 2, 2])
    np.testing.assert_array_equal(y, [0, 0, 0, 0])


def test_pointer_start_continues_the_sequence() -> None:
    """Decode two consecutive packets exactly as one packet."""
    first = decode_pointer_list(0, 20, TIMEBINS, SHAPE, snake_walk_xy=True, snake_walk_z=True)
    second = decode_pointer_list(20, 34, TIMEBINS, SHAPE, snake_walk_xy=True, snake_walk_z=True)
    whole = decode_pointer_list(0, SAMPLES, TIMEBINS, SHAPE, snake_walk_xy=True, snake_walk_z=True)

    for part_a, part_b, combined in zip(first, second, whole, strict=True):
        np.testing.assert_array_equal(np.concatenate([part_a, part_b]), combined)
