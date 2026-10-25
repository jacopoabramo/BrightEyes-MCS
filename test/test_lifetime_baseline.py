import numpy as np
import pytest

from brighteyes_mcs.acquisition.workers.acquisition_loop import flim_parameters_from_3samples
from brighteyes_mcs.ui.qt.main_window import MainWindow

BINS = 100
BIN_WIDTH_NS = 0.25
CYCLE_S = BINS * BIN_WIDTH_NS * 1e-9


def estimate(trace: np.ndarray) -> tuple[object, ...]:
    """Run the DFD decay fit on a trace of `BINS` bins.

    The fit reads no state of the window, so the window is never initialised.
    """
    seconds = np.arange(trace.size) * BIN_WIDTH_NS * 1e-9
    window = MainWindow.__new__(MainWindow)
    result: tuple[object, ...] = window.estimateDfdDecayLifetimeNs(
        trace, seconds, BIN_WIDTH_NS, BINS, CYCLE_S
    )
    return result


def test_decay_lifetime_recovers_a_single_exponential() -> None:
    """Fit 2.5 ns to a noise-free decay from its 95 % to its 25 % level."""
    bins = np.arange(BINS)
    trace = np.where(bins >= 10, np.exp(-(bins - 10) * BIN_WIDTH_NS / 2.5), 0.01)

    tau_ns, fit_curve, peak_idx, _, _ = estimate(trace)

    assert tau_ns == pytest.approx(2.5, rel=1e-9)
    assert peak_idx == 10
    assert isinstance(fit_curve, dict)
    assert fit_curve["fit_len"] == 14


def test_decay_lifetime_gives_no_fit_for_a_flat_trace() -> None:
    """Return no lifetime and no fit when the trace never falls below its peak."""
    tau_ns, fit_curve, peak_idx, _, _ = estimate(np.ones(BINS))

    assert tau_ns is None
    assert fit_curve is None
    assert peak_idx == 0


def test_decay_lifetime_rejects_a_trace_too_short_to_fit() -> None:
    """Return five None for a trace of fewer than four bins."""
    assert estimate(np.array([3.0, 2.0, 1.0])) == (None, None, None, None, None)


def test_three_sample_phase_of_a_single_window() -> None:
    """Place all light in the first window at its centre phase, measured back from the peak."""
    tau, brightness, quality, valid = flim_parameters_from_3samples(
        np.array([8.0]),
        np.array([0.0]),
        np.array([0.0]),
        cycle_period=1.0,
        sample_idx=np.array([1.5, 5.5, 9.5]),
        peak_idx=0,
        total_bins=12,
    )

    np.testing.assert_allclose(tau, [1 - 1.5 / 12])
    np.testing.assert_array_equal(brightness, [8.0])
    np.testing.assert_allclose(quality, [0.0], atol=1e-12)
    np.testing.assert_array_equal(valid, [True])


@pytest.mark.filterwarnings("ignore:invalid value encountered in divide:RuntimeWarning")
def test_three_sample_marks_a_dark_pixel_invalid() -> None:
    """Mark a pixel with no light invalid."""
    _, brightness, _, valid = flim_parameters_from_3samples(
        np.array([0.0]),
        np.array([0.0]),
        np.array([0.0]),
        cycle_period=1.0,
        sample_idx=np.array([1.5, 5.5, 9.5]),
        total_bins=12,
    )

    np.testing.assert_array_equal(brightness, [0.0])
    np.testing.assert_array_equal(valid, [False])
