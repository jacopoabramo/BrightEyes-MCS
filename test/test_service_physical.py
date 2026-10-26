"""Pin how the mcs service turns physical settings into register values and back."""

from typing import Any

import numpy as np
import pytest

from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.acquisition.settings import DfdConfig, LiveAnalysis, OutputConfig
from brighteyes_mcs.services.physical import (
    AUX_AXES,
    SETTINGS,
    RunSettings,
    Source,
    all_registers,
    derive,
    guarded_registers,
    held_during_run,
    run_config,
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


def merged(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the register groups of a run folded into one dictionary."""
    return {name: value for group in groups for name, value in group.items()}


def test_a_run_config_writes_what_the_window_writes() -> None:
    """Write the window's run registers, element for element, from the served settings."""
    config = window_config()
    run = RunSettings(repetitions=config.scan_area.repetitions, filename="run.h5", save=True)
    service = run_config(settings_of(config), run, config.detector)

    expected, actual = merged(run_registers(config)), merged(run_registers(service))

    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        np.testing.assert_allclose(
            np.asarray(actual[name], float), np.asarray(value, float), atol=1e-12, err_msg=name
        )


def test_a_run_config_carries_the_run_and_the_window_defaults() -> None:
    """Fill the output from the run settings and the pipeline values from the window defaults."""
    config = window_config()
    settings = settings_of(config)

    service = run_config(settings, RunSettings(3, "run.h5", False), config.detector)

    assert service.output == OutputConfig("run.h5", False, False, {})
    assert service.live == LiveAnalysis(10.0, 300.0, 20, True)
    assert service.dfd == DfdConfig(81, 1)
    assert service.scan_area.repetitions == 3
    assert service.detector.channels == (49 if settings["detector.channels_49"] else 25)


@pytest.mark.parametrize(
    ("path", "held"),
    [
        ("grid.pixels", True),
        ("pattern.enabled", True),
        ("detector.dfd", True),
        ("analog_in.selector_a", True),
        ("scanner.x.range_um", True),
        ("scanner.x.calibration_um_per_volt", True),
        ("timing.laser_sequence", True),
        ("aux.x2.position_um", False),
        ("aux.x2.calibration_um_per_volt", False),
        ("lasers.1.enabled", False),
        ("analog_out.3.source", False),
    ],
)
def test_settings_held_during_a_run_are_groups_a_and_b(path: str, held: bool) -> None:
    """Hold the settings of lock groups A and B during a run and let group C through."""
    assert held_during_run(path) is held


def test_guarded_registers_are_those_of_groups_a_and_b_and_the_run() -> None:
    """Guard the registers groups A and B write, the run registers and the commands only."""
    guarded = guarded_registers()

    assert {
        "max_pixel",
        "axis_calibration_volts_per_step",
        "stream_out_main_enable",
        "max_repetition",
        "dfd_trigger_selector",
        "start_command",
        "stop_command",
    } <= guarded
    assert (
        not {
            "laser_1_enable",
            "analog_output_0_dc_volts",
            "analog_output_0_source_selector",
        }
        & guarded
    )
