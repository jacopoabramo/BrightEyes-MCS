"""Pin how the mcs service turns physical settings into register values and back."""

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.services.physical import SETTINGS, all_registers, served, writes
from test.window_settings import settings_of, window_config


def test_settings_write_what_the_window_writes() -> None:
    """Compute, for each register a setting writes, the value `run_registers` writes."""
    config = window_config()
    expected = {name: value for group in run_registers(config) for name, value in group.items()}
    expected.pop("max_repetition")
    expected.pop("dfd_trigger_selector")

    actual = all_registers(settings_of(config))

    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        np.testing.assert_allclose(
            np.asarray(actual[name], float), np.asarray(value, float), err_msg=name
        )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("grid.pixels", ("axis_calibration_volts_per_step", "max_pixel")),
        (
            "scanner.x.calibration_um_per_volt",
            ("circular_scan_x_volts", "axis_calibration_volts_per_step", "axis_start_offset_volts"),
        ),
        ("aux.x2.position_um", ("analog_output_4_dc_volts",)),
        ("analog_out.3.source", ("analog_output_3_source_selector", "analog_output_3_dc_volts")),
        ("pattern.enabled", ("circular_scan_enable",)),
    ],
)
def test_a_put_writes_only_the_registers_its_value_enters(
    path: str, expected: tuple[str, ...]
) -> None:
    """Name, in write order, the registers a put of each setting writes."""
    assert writes(path, settings_of(window_config())) == expected


def test_a_setting_missing_a_register_is_not_served() -> None:
    """Leave out a setting whose register the bitfile lacks, and keep its siblings."""
    names = {name for setting in SETTINGS.values() for name in setting.registers}

    paths = served(names - {"max_circular_point"})

    assert "pattern.point_count" not in paths
    assert "pattern.enabled" in paths
