"""Pin how the mcs service turns physical settings into register values and back."""

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.services.physical import (
    AUX_AXES,
    SETTINGS,
    Source,
    all_registers,
    derive,
    served,
    tolerance,
    writes,
)
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


def test_settings_read_back_from_the_registers_they_wrote() -> None:
    """Derive every setting from its own registers within its tolerance."""
    settings = settings_of(window_config())
    raw = all_registers(settings)
    held = {path: value for path, value in settings.items() if SETTINGS[path].held}
    steps = dict.fromkeys(raw, 2**-15)

    derived, failures = derive(raw, held, SETTINGS)

    assert failures == {}
    assert derived.keys() == {path for path, setting in SETTINGS.items() if not setting.held} | {
        f"aux.{axis}.position_um" for axis in AUX_AXES
    }
    for path, value in derived.items():
        allowed = tolerance(path, settings, steps) + 1e-12
        match SETTINGS[path].kind:
            case "floats" | "ints":
                np.testing.assert_allclose(value, settings[path], atol=allowed, err_msg=path)
            case "float":
                assert value == pytest.approx(settings[path], abs=allowed), path
            case _:
                assert value == settings[path], path


def test_an_unknown_selector_is_reported_not_raised() -> None:
    """Report a source selector that names no source as a failure of that setting only."""
    settings = settings_of(window_config())
    raw = all_registers(settings)
    raw["analog_output_2_source_selector"] = 12
    held = {path: value for path, value in settings.items() if SETTINGS[path].held}

    derived, failures = derive(raw, held, SETTINGS)

    assert set(failures) == {"analog_out.2.source"}
    assert derived["analog_out.3.source"] is Source.CONSTANT


def test_an_auxiliary_position_no_output_sends_keeps_its_held_value() -> None:
    """Keep the held position of an auxiliary axis that no output sends."""
    settings = settings_of(window_config())
    held = {path: value for path, value in settings.items() if SETTINGS[path].held}

    derived, _ = derive(all_registers(settings), held, SETTINGS)

    assert derived["aux.y2.position_um"] == 3.0
