"""Pin the register values the main window writes, through any refactoring."""

import copy
import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from brighteyes_mcs.acquisition.detectors.models import DETECTOR_PISPAD23, DETECTOR_SPAD_ARRAY
from brighteyes_mcs.acquisition.manager import McsManager
from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.acquisition.settings import AcquisitionConfig
from brighteyes_mcs.ui.qt.main_window import MainWindow


class Widget:
    """Stand-in for a Qt input widget holding one fixed value."""

    def __init__(self, value, decimals=None, index=None):
        self._value = value
        self._decimals = decimals
        self._index = index

    def value(self):
        return self._value

    def isChecked(self):
        return bool(self._value)

    def text(self):
        return str(self._value)

    def currentText(self):
        return str(self._value)

    def currentIndex(self):
        if self._index is not None:
            return self._index
        return self._value if isinstance(self._value, int) else 0

    def blockSignals(self, _blocked):
        return False

    def setText(self, _text):
        pass

    def setMaximum(self, _maximum):
        pass

    def setValue(self, value):
        self._value = round(value, self._decimals) if self._decimals is not None else value


class FakeUi:
    """Window `ui` that returns a configured widget by name, else a mock."""

    def __init__(self, widgets):
        self._widgets = widgets
        self._mocks = {}

    def __getattr__(self, name):
        if name in self._widgets:
            return self._widgets[name]
        return self._mocks.setdefault(name, MagicMock())


ANALOG_OUTPUTS = (
    ("X", 0, 0.5),
    ("Y", 1, -0.25),
    ("Z", 2, 1.125),
    ("Constant", 3, 2.375),
    ("Laser 1", 4, -1.5),
    ("X2", 8, 0.0),
    ("Y2", 9, 0.0),
    ("Z2", 10, 0.0),
)


def make_widgets() -> dict[str, Any]:
    """Return fresh widgets holding distinct, realistic settings."""
    values = {
        "spinBox_range_x": 12.5,
        "spinBox_range_y": 9.75,
        "spinBox_range_z": 3.2,
        "spinBox_off_x_um": 1.5,
        "spinBox_off_y_um": -2.25,
        "spinBox_off_z_um": 0.8,
        "spinBox_calib_x": 40.0,
        "spinBox_calib_y": 32.0,
        "spinBox_calib_z": 8.0,
        "spinBox_offExtra_x_V": 0.05,
        "spinBox_offExtra_y_V": -0.12,
        "spinBox_offExtra_z_V": 0.07,
        "spinBox_min_x_V": -4.1,
        "spinBox_min_y_V": -3.9,
        "spinBox_min_z_V": -2.6,
        "spinBox_max_x_V": 4.3,
        "spinBox_max_y_V": 3.7,
        "spinBox_max_z_V": 2.9,
        "spinBox_off_x2_um": 6.0,
        "spinBox_calib_x_2": 25.0,
        "spinBox_offExtra_x_V_2": 0.11,
        "spinBox_min_x_V_2": -1.3,
        "spinBox_max_x_V_2": 1.6,
        "spinBox_off_y2_um": -3.5,
        "spinBox_calib_y_2": 14.0,
        "spinBox_offExtra_y_V_2": -0.06,
        "spinBox_min_y_V_2": 2.2,
        "spinBox_max_y_V_2": -2.4,
        "spinBox_off_z2_um": 90.0,
        "spinBox_calib_z_2": 30.0,
        "spinBox_offExtra_z_V_2": 0.02,
        "spinBox_min_z_V_2": -0.9,
        "spinBox_max_z_V_2": 0.95,
        "spinBox_nx": 64,
        "spinBox_ny": 48,
        "spinBox_nframe": 5,
        "spinBox_nrepetition": 3,
        "spinBox_timeresolution": 1.25,
        "spinBox_time_bin_per_px": 81,
        "spinBox_waitForLaser": 0.2,
        "spinBox_waitAfterFrame": 0.05,
        "checkBox_waitOnlyFirstTime": True,
        "checkBox_circular": True,
        "spinBox_circular_radius_nm": 350.0,
        "spinBox_circular_points": 24,
        "spinBox_circular_repetition": 7,
        "checkBox_lissajous": True,
        "spinBox_lissajous_omega_x": 3,
        "spinBox_lissajous_omega_y": 2,
        "spinBox_lissajous_phase_deg": 30.0,
        "spinBox_lissajous_firstposition": 1,
        "checkBox_lissajous_opencurve": False,
        "checkBox_laser0": True,
        "checkBox_laser1": False,
        "checkBox_laser2": True,
        "checkBox_laser3": False,
        "checkBox_DummyData": True,
        "checkBox_slavemode_enable": True,
        "comboBox_slavemode_type": 1,
        "checkBox_SPAD_VR0": True,
        "checkBox_SPAD_VR1": False,
        "checkBox_snake": True,
        "checkBox_snake_z": True,
        "checkBox_DFD_LaserDebug": True,
        "checkBox_DFD": False,
        "spinBox_DFD_nbins": 50,
        "checkBox_fifo_digital": True,
        "checkBox_fifo_analog": True,
        "checkBox_analog_in_integrate_AI0": True,
        "checkBox_analog_in_integrate_AI1": False,
        "checkBox_analog_in_integrate_AI2": True,
        "checkBox_analog_in_integrate_AI3": False,
        "checkBox_analog_in_invert_AI0": False,
        "checkBox_analog_in_invert_AI1": True,
        "checkBox_analog_in_invert_AI2": False,
        "checkBox_analog_in_invert_AI3": True,
        "comboBox_analogSelect_A": 2,
        "comboBox_analogSelect_B": 3,
        "checkBox_analog_in_differentiate_A": True,
        "checkBox_analog_in_differentiate_B": False,
        "comboBox_spad_channels": "25",
        "checkBoxLockRatio": False,
        "checkBox_showPreview": False,
        "checkBox_uttmActivate": False,
        "checkBox_uttm_auto": False,
        "checkBox_pispad23ttmActivate": False,
        "doubleSpinBox_binsize": 0.013,
        "doubleSpinBox_maxlength": 0.0021,
        "spinBox_compensation_delay": 7,
        "spinBox_FCSbins": 20,
        "spinBox_clk_base_multiplier": 3,
        "spinBox_pispad23ttm_stream_port": 9998,
        "spinBox_pispad23ttm_uimg_batch": 64,
        "lineEdit_pispad23_ip_addr": "10.0.0.5",
        "spinBox_pispad23_port": 9997,
        "lineEdit_ni_addr": "RIO0",
        "lineEdit_fpgabitfile": "bitfiles/MyBitfileUSB.lvbitx",
    }
    sequence = (1, 2, 4, 8, 3, 5, 6, 7, 9, 10, 11, 12)
    values.update({f"comboLaserSeq_{n}": laser for n, laser in enumerate(sequence, 1)})
    widgets = {name: Widget(value) for name, value in values.items()}
    widgets["comboBox_AnalogOut"] = {
        channel: Widget(source, index=index)
        for channel, (source, index, _) in enumerate(ANALOG_OUTPUTS)
    }
    widgets["spinBox_AnalogOut"] = {
        channel: Widget(volts, decimals=4) for channel, (_, _, volts) in enumerate(ANALOG_OUTPUTS)
    }
    widgets["checkBox_AnalogOut"] = {channel: Widget(channel % 2 == 0) for channel in range(8)}
    return widgets


COLLABORATORS = (
    "rect_roi",
    "timerPreviewImg",
    "marker_plot_circular_scan",
    "lissajous_mini_curve",
    "lissajous_mini_points",
    "lissajous_mini_first_point",
    "lissajous_mini_plot",
    "updateRectLimit",
    "checkAlerts",
    "defineFilename",
    "defineMetadataFilename",
    "fingerprint_markers_mask",
    "plugin_signals",
)


def make_window(writes: list[dict[str, Any]], manager: McsManager | None = None) -> MainWindow:
    """Return a window over fake widgets that records each register write in `writes`.

    Given a manager, the window writes through it as in production and
    `writes` is left to the caller.
    """
    window = MainWindow.__new__(MainWindow)
    window.ui = FakeUi(make_widgets())
    window.mcs_manager = MagicMock() if manager is None else manager
    window.configurationFPGA_dict = {}
    window.clock_base = 40
    window.spad_channels = 25
    window.lock_parameters_changed_call = False
    window._mcs_saving_suppressed = False
    for name in COLLABORATORS:
        setattr(window, name, MagicMock())
    window.defineFilename = MagicMock(return_value="C:/data/run.h5")
    window.defineMetadataFilename = MagicMock(return_value="C:/data/run_only_metadata.h5")
    window.ttm_remote_is_up = MagicMock(return_value=False)
    window._current_detector_model = MagicMock(return_value="SPAD Array")
    if manager is None:
        window.setRegistersDict = lambda registers: writes.append(copy.deepcopy(registers))
    return window


def record_start(do_run: bool = True) -> tuple[list[dict[str, Any]], McsManager]:
    """Return the register writes of a start and the manager that received them."""
    writes: list[dict[str, Any]] = []
    manager = McsManager()
    manager.is_connected = True
    manager.fpga_handle = MagicMock()
    manager.run = MagicMock()
    manager.shared_arrays_ready = True
    manager.set_fingerprint_mask = MagicMock()
    write = manager.set_registers_dict

    def record(registers: Mapping[str, Any]) -> None:
        writes.append(copy.deepcopy(dict(registers)))
        write(registers)

    manager.set_registers_dict = record
    window = make_window(writes, manager=manager)
    window.initializeAcquisition(do_not_save=True, do_run=do_run)
    return writes, manager


def record_start_writes() -> list[dict[str, Any]]:
    """Return the register dictionaries the start sequence writes, in order."""
    return record_start()[0]


LIVE_SLOTS = {
    "temporalSettingsChanged": lambda window: window.temporalSettingsChanged(),
    "positionSettingsChanged_apply": lambda window: window.positionSettingsChanged_apply(
        force=True
    ),
    "laserChanged": lambda window: window.laserChanged(),
    "updateMaxMinVoltages": lambda window: window.updateMaxMinVoltages(),
    "analogOutChanged": lambda window: window.analogOutChanged(),
    "auxiliaryPositionChanged": lambda window: window.auxiliaryPositionChanged(),
    "circularMotionActivateChanged": lambda window: window.circularMotionActivateChanged(),
    "configure_analog": lambda window: window.configure_analog(),
    "configure_stream_enables": lambda window: window.configure_stream_enables(),
}


def record_live_writes():
    """Return the register dictionaries each live slot writes, keyed by slot name."""
    recorded = {}
    for slot, call in LIVE_SLOTS.items():
        writes = []
        window = make_window(writes)
        window.dfd_enable = False
        call(window)
        recorded[slot] = writes
    return recorded


def to_json(value):
    """Return `value` with NumPy arrays and scalars turned into plain lists and numbers."""
    if isinstance(value, (np.ndarray, np.generic)):
        return value.tolist()
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json(item) for item in value]
    return value


def value_types(value: Any) -> Any:
    """Return the type name of `value`, element by element for a list."""
    if isinstance(value, list):
        return [value_types(item) for item in value]
    return type(value).__name__


def assert_same_value(actual: Any, expected: Any, name: str) -> None:
    """Assert that `actual` equals the recorded `expected` in value and type."""
    actual = to_json(actual)
    assert value_types(actual) == value_types(expected), name
    if "float" in str(value_types(expected)):
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12, err_msg=name)
    else:
        assert actual == expected, name


def assert_same_writes(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    """Assert that each write holds the recorded registers, in value and type."""
    assert len(actual) == len(expected)
    for actual_registers, expected_registers in zip(actual, expected, strict=True):
        assert actual_registers.keys() == expected_registers.keys()
        for name, expected_value in expected_registers.items():
            assert_same_value(actual_registers[name], expected_value, name)


BASELINE = json.loads(
    (Path(__file__).parent / "data" / "register_writes.json").read_text(encoding="utf-8")
)


def test_start_sequence_writes_match_baseline():
    """Write the same register dictionaries, in the same order, as before the move."""
    assert_same_writes(record_start_writes(), BASELINE["start"])


@pytest.mark.parametrize("slot", sorted(BASELINE["live"]))
def test_live_slot_writes_match_baseline(slot):
    """Write the same register dictionaries from each live slot as before the move."""
    assert_same_writes(record_live_writes()[slot], BASELINE["live"][slot])


def test_harness_rejects_a_changed_value_type() -> None:
    """Fail the comparison when a value keeps its number but changes type."""
    with pytest.raises(AssertionError):
        assert_same_writes([{"max_pixel": 1}], [{"max_pixel": 1.0}])


def record_start_settings() -> dict[str, Any]:
    """Return the settings a start leaves in the manager, under the setter that sets each."""
    _, manager = record_start()
    settings = {
        "set_spad_channels": [manager.spad_channels],
        "set_dfd_enable": [manager.dfd_enable],
        "set_dfd_nbins": [manager.dfd_nbins],
        "set_activate_snake_walk_xy": [manager.snake_walk_xy],
        "set_activate_snake_walk_z": [manager.snake_walk_z],
        "set_compensation_delay_for_snake": [manager.compensation_delay_for_snake],
        "set_activated_fifo": [manager.activated_fifos_list],
        "set_show_preview": [manager.activate_show_preview],
        "set_do_not_save": [manager.do_not_save_event.is_set()],
        "set_raw_stream_mode": [manager.raw_stream_mode],
        "set_filename_h5": [manager.filenameh5],
        "set_autocorrelation_maxx": [manager.autocorrelation_maxx],
        "set_trace_bins": [manager.trace_bins],
        "set_trace_sample_per_bins": [manager.trace_sample_per_bins],
        "set_clk_multiplier": [manager.clk_multiplier],
        "set_fingerprint_mask": list(manager.set_fingerprint_mask.call_args.args),
        "pispad23_stream_port": manager.pispad23_stream_port,
        "pispad23_batch_size": manager.pispad23_batch_size,
    }
    return to_json(settings)


def test_start_sequence_settings_match_baseline() -> None:
    """Pass the manager the same settings as before the move."""
    actual = record_start_settings()
    assert actual.keys() == BASELINE["start_settings"].keys()
    for name, expected in BASELINE["start_settings"].items():
        assert_same_value(actual[name], expected, name)


def start_config(**fields: Any) -> AcquisitionConfig:
    """Return the window's run configuration for the harness widgets, with `fields` replaced."""
    window = make_window([])
    window.dfd_enable = False
    window._sync_auxiliary_position_outputs()
    config = window._acquisition_config(True, False, "C:/data/run.h5", {})
    return dataclasses.replace(config, **fields)


def test_run_registers_match_baseline() -> None:
    """Return the eight start dictionaries of the baseline, in order."""
    assert_same_writes(run_registers(start_config()), BASELINE["start"][:8])


def test_run_registers_skip_pattern_without_circular_scan() -> None:
    """Leave out the circular pattern when the circular scan is off."""
    config = start_config()
    options = dataclasses.replace(config.options, circular_scan=False)
    writes = run_registers(dataclasses.replace(config, options=options))
    assert len(writes) == 7
    assert all("circular_scan_x_volts" not in registers for registers in writes)


def test_run_registers_skip_streams() -> None:
    """Leave out the stream enables for the test-mode start."""
    assert_same_writes(run_registers(start_config(), streams=False), BASELINE["start"][:7])


def test_run_registers_set_49_channel_mode() -> None:
    """Turn on 49-channel mode for a 49-channel detector."""
    config = start_config()
    detector = dataclasses.replace(config.detector, channels=49)
    writes = run_registers(dataclasses.replace(config, detector=detector))
    assert writes[2] == {"detector_49_channel_mode_enable": True}


@pytest.fixture
def manager() -> McsManager:
    """Return a manager connected to a recording FPGA handle."""
    instance = McsManager()
    instance.is_connected = True
    instance.fpga_handle = MagicMock()
    return instance


def test_prepare_run_writes_run_registers(manager: McsManager) -> None:
    """Write each start dictionary in order and return them merged."""
    config = start_config()
    written = manager.prepare_run(config)
    expected = run_registers(config)
    merged = {name: value for registers in expected for name, value in registers.items()}
    assert_same_writes([written], [to_json(merged)])
    assert [call.args[0] for call in manager.fpga_handle.register_write_checked.call_args_list] == [
        name for registers in expected for name in registers
    ]


@pytest.mark.parametrize(("dfd", "multiplier"), [(False, 1), (True, 3)])
def test_prepare_run_clock_multiplier(manager: McsManager, dfd: bool, multiplier: int) -> None:
    """Use the DFD clock multiplier only while DFD is on."""
    config = start_config()
    streams = dataclasses.replace(config.streams, dfd=dfd)
    manager.prepare_run(dataclasses.replace(config, streams=streams))
    assert manager.clk_multiplier == multiplier


@pytest.mark.parametrize(
    ("model", "host"), [(DETECTOR_PISPAD23, "10.0.0.5"), (DETECTOR_SPAD_ARRAY, "127.0.0.1")]
)
def test_prepare_run_pispad23_connection(manager: McsManager, model: str, host: str) -> None:
    """Set the PISPAD23 host only for a detector on the PISPAD23 pipeline."""
    config = start_config()
    detector = dataclasses.replace(config.detector, model=model)
    manager.prepare_run(dataclasses.replace(config, detector=detector))
    assert manager.pispad23_host == host


def test_prepare_run_raw_stream(manager: McsManager) -> None:
    """Set the raw output files and hide the preview in raw stream mode."""
    window = make_window([])
    window.dfd_enable = False
    window.ui.checkBox_showPreview.setValue(True)
    files = {"stream_out_main": "C:/data/run_FIFO.raw"}
    manager.prepare_run(
        window._acquisition_config(False, True, "C:/data/run_only_metadata.h5", files)
    )
    assert manager.raw_output_files == files
    assert manager.activate_show_preview is False


def test_start_pulses_run_command(manager: McsManager) -> None:
    """Clear stop and raise start, then lower start, as one fresh edge per run."""
    assert manager.start() == {"stop_command": False, "start_command": False}
    assert [call.args for call in manager.fpga_handle.register_write_checked.call_args_list] == [
        ("stop_command", False),
        ("start_command", True),
        ("start_command", False),
    ]


def test_test_mode_start_writes_no_streams() -> None:
    """Write neither stream enables nor the start command, and select no FIFOs, in the test-mode start."""
    writes, manager = record_start(do_run=False)
    assert_same_writes(writes, BASELINE["start"][:7])
    assert manager.activated_fifos_list == []
