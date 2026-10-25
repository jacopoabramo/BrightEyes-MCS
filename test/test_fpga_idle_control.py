from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from brighteyes_mcs.acquisition.manager import McsManager
from brighteyes_mcs.hardware.fpga import FpgaHandle
from brighteyes_mcs.acquisition.workers.fpga import validate_fpga_interface
from brighteyes_mcs.ui.qt.main_window import MainWindow


def bare_manager():
    manager = McsManager.__new__(McsManager)
    manager.is_connected = True
    manager.fpga_handle = MagicMock()
    manager.registers_configuration = {}
    return manager


def test_quick_reset_pulses_stop_and_waits_for_idle():
    manager = bare_manager()
    manager.wait_for_fpga_idle = MagicMock()

    manager.quick_reset_fpga(timeout=2.5)

    assert manager.fpga_handle.register_write_checked.call_args_list == [
        call("stop_command", True),
        call("stop_command", False),
    ]
    assert manager.registers_configuration["stop_command"] is False
    manager.wait_for_fpga_idle.assert_called_once_with(
        timeout=2.5, poll_interval=0.01
    )


def test_wait_for_fpga_idle_returns_on_status_zero():
    manager = bare_manager()
    manager.fpga_handle.register_read.side_effect = [
        {"debug_scan_fsm_status": 3},
        {"debug_scan_fsm_status": 0},
    ]

    manager.wait_for_fpga_idle(timeout=1, poll_interval=0)

    assert manager.registers_configuration["debug_scan_fsm_status"] == 0
    assert manager.fpga_handle.register_read.call_count == 2


def test_wait_for_fpga_idle_raises_after_timeout():
    manager = bare_manager()
    manager.fpga_handle.register_read.return_value = {"debug_scan_fsm_status": 4}

    with pytest.raises(TimeoutError, match="last status: 4"):
        manager.wait_for_fpga_idle(timeout=0.001, poll_interval=0)


def test_fpga_watchdog_reads_status_register():
    manager = bare_manager()
    manager.fpga_handle.register_read.return_value = {
        "debug_scan_fsm_status": 2
    }

    assert manager.check_fpga_alive() == 2
    manager.fpga_handle.register_read.assert_called_once_with(
        ("debug_scan_fsm_status",)
    )
    assert manager.registers_configuration["debug_scan_fsm_status"] == 2


def test_runfpga_waits_until_fpga_vi_is_running():
    handle = FpgaHandle.__new__(FpgaHandle)
    started_event = MagicMock()
    started_event.is_set.return_value = False
    started_event.wait.return_value = True
    run_request = MagicMock()
    handle.configuration = {
        "detector_model": "SPAD Array",
        "fpgarunning": run_request,
        "fpga_started": started_event,
    }

    handle.runfpga(timeout=2.5)

    run_request.set.assert_called_once_with()
    started_event.wait.assert_called_once_with(timeout=2.5)


def test_firmware_validation_reports_missing_control_registers():
    with pytest.raises(
        RuntimeError,
        match="missing registers: debug_scan_fsm_status, stop_command",
    ):
        validate_fpga_interface(
            available_registers={"start_command"},
            available_fifos={"stream_out_main"},
            required_fifos=["stream_out_main"],
        )


def test_firmware_validation_reports_missing_requested_fifo():
    with pytest.raises(RuntimeError, match="missing DMA FIFOs: stream_out_main"):
        validate_fpga_interface(
            available_registers={
                "start_command",
                "stop_command",
                "debug_scan_fsm_status",
            },
            available_fifos=set(),
            required_fifos=["stream_out_main"],
        )


def test_fpga_handle_propagates_worker_initialization_error():
    handle = FpgaHandle.__new__(FpgaHandle)
    ready_event = MagicMock()
    initialization_error = {}

    def finish_initialization(timeout):
        initialization_error["message"] = "firmware is incompatible"
        return True

    ready_event.wait.side_effect = finish_initialization
    handle.configuration = {
        "initial_registers": {},
        "initialization_error": initialization_error,
        "is_readytorun": ready_event,
        "is_connected": MagicMock(),
        "detector_model": "SPAD Array",
    }
    handle.use_rust_fifo = False

    with patch(
        "brighteyes_mcs.hardware.fpga.NiFpgaControlProcess"
    ) as process_type:
        with pytest.raises(RuntimeError, match="firmware is incompatible"):
            handle.run({"start_command": False})

    process_type.return_value.start.assert_called_once_with()


def test_run_command_is_pulsed():
    """Pulse the run command, because the session stays open between runs."""
    window = MainWindow.__new__(MainWindow)
    window.setRegistersDict = MagicMock()

    window.sendCmdRun()

    assert window.setRegistersDict.call_args_list == [
        call({"stop_command": False, "start_command": True}),
        call({"start_command": False}),
    ]


def connected_window():
    window = MainWindow.__new__(MainWindow)
    window.FPGA_IDLE_TIMEOUT_SECONDS = 5.0
    window.ui = MagicMock()
    window.ui.checkBox_pulsing_forced.isChecked.return_value = False
    window.ui.checkBox_DFD.isChecked.return_value = False
    window._current_detector_model = MagicMock(return_value="spad")
    window.spad_channels = 25
    window.configurationFPGA_dict = {}
    window.mcs_manager = MagicMock(is_connected=True)
    window._connected_settings = window._connection_settings()
    session = MagicMock()
    window.disconnectFPGA = session.disconnect
    window.connectFPGA = session.connect
    return window, session


def test_run_refuses_to_start_without_a_session():
    """Refuse to start a run while disconnected instead of connecting."""
    window, session = connected_window()
    window.mcs_manager.is_connected = False

    with pytest.raises(RuntimeError, match="not connected"):
        window._prepare_fpga_for_acquisition()

    session.connect.assert_not_called()
    window.mcs_manager.quick_reset_fpga.assert_not_called()


def test_run_resets_fpga_and_replays_controls_without_command_edges():
    """Reset the scan before a run and replay controls, never command edges."""
    window, session = connected_window()
    window.ui.checkBox_pulsing_forced.isChecked.return_value = True
    window.configurationFPGA_dict = {"laser_force_pulsing_enable": True, "start_command": True}

    window._prepare_fpga_for_acquisition()

    assert session.mock_calls == []
    window.mcs_manager.quick_reset_fpga.assert_called_once_with(timeout=5.0)
    window.mcs_manager.set_registers_dict.assert_any_call({"laser_force_pulsing_enable": True})
    window.mcs_manager.set_registers_dict.assert_any_call({"laser_time_bin_mode_enable": True, "max_laser_time_bin": 1})
    assert all("start_command" not in c.args[0] for c in window.mcs_manager.set_registers_dict.call_args_list)


@pytest.mark.parametrize(
    ("widget", "accessor", "value"),
    [
        ("lineEdit_fpgabitfile", "text", "other.lvbitx"),
        ("checkBox_fifo_analog", "isChecked", True),
    ],
)
def test_changed_connection_setting_reopens_session_before_run(widget, accessor, value):
    """Close and reopen the session before a run when a setting fixed at connect changed."""
    window, session = connected_window()
    getattr(getattr(window.ui, widget), accessor).return_value = value

    window._prepare_fpga_for_acquisition()

    assert session.mock_calls == [call.disconnect(), call.connect()]
    window.mcs_manager.quick_reset_fpga.assert_called_once_with(timeout=5.0)


def test_completed_filename_is_published_to_console_as_absolute_path(tmp_path):
    window = MainWindow.__new__(MainWindow)
    window.console_widget = MagicMock()
    filename = tmp_path / "acquisition.h5"

    window._publish_filename_to_console(str(filename))

    window.console_widget.push_vars.assert_called_once_with(
        {"filename": str(filename.resolve())}
    )


def window_with_controls(connected):
    window = MainWindow.__new__(MainWindow)
    window.ui = SimpleNamespace(
        checkBox_fpga_connect_at_startup=MagicMock(),
        pushButton_fpga_connection_cmd=MagicMock(),
        pushButton_previewStart=MagicMock(),
        pushButton_acquisitionStart=MagicMock(),
        label_FPGA_status=MagicMock(),
        statusBar=MagicMock(),
    )
    window.mcs_manager = MagicMock(is_connected=connected)
    window.timerPreviewImg = MagicMock()
    window.started_normal = False
    window.started_preview = False
    return window


def test_stop_leaves_session_open():
    """Reset the scan after a run without closing the FPGA session."""
    window = window_with_controls(connected=True)

    window.stopAcquisition()

    window.mcs_manager.quick_reset_fpga.assert_called_once_with(timeout=5.0)
    window.mcs_manager.stop_acquisition.assert_called_once_with()
    window.mcs_manager.stop_fpga.assert_not_called()


def test_failed_stop_reset_closes_session():
    """Close the session when the scan does not return to idle after a run."""
    window = window_with_controls(connected=True)
    window.mcs_manager.quick_reset_fpga.side_effect = TimeoutError("not idle")

    with pytest.raises(TimeoutError):
        window.stopAcquisition()

    window.mcs_manager.stop_acquisition.assert_called_once_with()
    window.mcs_manager.stop_fpga.assert_called_once_with()


@pytest.mark.parametrize("enabled", [True, False])
def test_startup_connects_only_when_setting_is_on(enabled):
    """Open the session at startup only when the setting asks for it."""
    window = window_with_controls(connected=False)
    window.ui.checkBox_fpga_connect_at_startup.isChecked.return_value = enabled
    window.connectFPGA = MagicMock()
    window._fpgaWatchdogTick = MagicMock()

    window._connect_fpga_at_startup()

    assert window.connectFPGA.called is enabled


def test_failed_startup_connect_leaves_runs_disabled():
    """Show the error once and keep Preview and Acquisition disabled after a failed startup connect."""
    window = window_with_controls(connected=False)
    window.ui.checkBox_fpga_connect_at_startup.isChecked.return_value = True
    error = RuntimeError("no board")
    window.connectFPGA = MagicMock(side_effect=error)
    window._show_fpga_initialization_error = MagicMock()

    window._connect_fpga_at_startup()

    window._show_fpga_initialization_error.assert_called_once_with(error)
    for button in (window.ui.pushButton_previewStart, window.ui.pushButton_acquisitionStart):
        button.setEnabled.assert_called_with(False)
        assert call(True) not in button.setEnabled.call_args_list


def test_connect_fpga_forces_fsm_commands_low():
    window = MainWindow.__new__(MainWindow)
    window.ui = MagicMock()
    window.ui.lineEdit_fpgabitfile.text.return_value = "primary.lvbitx"
    window.ui.lineEdit_fpga2bitfile.text.return_value = ""
    window.ui.lineEdit_ni_addr.text.return_value = "RIO0"
    window.ui.lineEdit_ni2addr.text.return_value = ""
    window.ui.lineEdit_spad_data.text.return_value = "0"
    window.ui.lineEdit_spad_length.text.return_value = "0"
    window.ui.comboBox_fifobackend.currentText.return_value = "Python"
    window.ui.checkBox_fifo_analog.isChecked.return_value = False
    window.ui.checkBox_fifo_digital.isChecked.return_value = True
    window.bitfile_check = MagicMock(return_value="primary.lvbitx")
    window._current_detector_model = MagicMock(return_value="spad")
    window.configurationFPGA_dict = {
        "start_command": True,
        "stop_command": True,
    }
    window.spad_channels = 25
    window.mcs_manager = MagicMock(is_connected=False)
    window.mcs_manager.default_configuration = {}

    window.connectFPGA()

    initial_registers = window.mcs_manager.connect.call_args.args[0]
    assert initial_registers["start_command"] is False
    assert initial_registers["stop_command"] is False


def test_connect_button_enables_runs():
    """Connect from the button and enable Preview and Acquisition."""
    window = window_with_controls(connected=False)

    def connect():
        window.mcs_manager.is_connected = True

    window.connectFPGA = MagicMock(side_effect=connect)
    window._fpgaWatchdogTick = MagicMock()

    window.fpgaConnectionButtonClicked(True)

    window.connectFPGA.assert_called_once_with()
    window._fpgaWatchdogTick.assert_called_once_with()
    window.ui.pushButton_fpga_connection_cmd.setChecked.assert_called_with(True)
    window.ui.pushButton_fpga_connection_cmd.setText.assert_called_with("Disconnect FPGA")
    window.ui.pushButton_previewStart.setEnabled.assert_called_with(True)
    window.ui.pushButton_acquisitionStart.setEnabled.assert_called_with(True)


def test_disconnect_button_stops_running_acquisition_first():
    """Stop a running acquisition before disconnecting from the button."""
    window = window_with_controls(connected=True)
    window.started_normal = True

    def stop_running_acquisition():
        window.mcs_manager.is_connected = False

    window.stop = MagicMock(side_effect=stop_running_acquisition)

    window.fpgaConnectionButtonClicked(False)

    window.stop.assert_called_once_with()
    window.ui.pushButton_fpga_connection_cmd.setChecked.assert_called_with(False)
    window.ui.pushButton_fpga_connection_cmd.setText.assert_called_with("Connect FPGA")


def test_disconnect_fpga_closes_session_and_disables_runs():
    """Close the session on disconnect and disable Preview and Acquisition."""
    window = window_with_controls(connected=True)
    window.FPGA_IDLE_TIMEOUT_SECONDS = 5.0
    window._fpga_watchdog_blink_on = True

    window.disconnectFPGA()

    window.mcs_manager.quick_reset_fpga.assert_called_once_with(timeout=5.0)
    window.mcs_manager.stop_fpga.assert_called_once_with()
    window.mcs_manager.stop_acquisition.assert_called_once_with()
    assert window.mcs_manager.is_connected is False
    window.ui.pushButton_fpga_connection_cmd.setChecked.assert_called_with(False)
    window.ui.pushButton_previewStart.setEnabled.assert_called_with(False)
    window.ui.pushButton_acquisitionStart.setEnabled.assert_called_with(False)
    window.ui.label_FPGA_status.setText.assert_called_with("● FPGA disconnected")
    window.ui.label_FPGA_status.setToolTip.assert_called_with(
        "Click Connect FPGA to open the FPGA session."
    )


def test_watchdog_blinks_green_after_successful_register_read():
    window = MainWindow.__new__(MainWindow)
    label = MagicMock()
    window.ui = SimpleNamespace(label_FPGA_status=label)
    window.mcs_manager = MagicMock(is_connected=True)
    window.mcs_manager.check_fpga_alive.return_value = 0
    window._fpga_watchdog_blink_on = False

    window._fpgaWatchdogTick()

    label.setText.assert_called_once_with("● FPGA connected")
    label.setStyleSheet.assert_called_once_with("color: #00e676;")
    assert window._fpga_watchdog_blink_on is True


def test_watchdog_reports_failed_register_read():
    window = MainWindow.__new__(MainWindow)
    label = MagicMock()
    window.ui = SimpleNamespace(label_FPGA_status=label)
    window.mcs_manager = MagicMock(is_connected=True)
    window.mcs_manager.check_fpga_alive.side_effect = RuntimeError("read failed")
    window._fpga_watchdog_blink_on = True

    window._fpgaWatchdogTick()

    label.setText.assert_called_once_with("● FPGA not responding")
    label.setStyleSheet.assert_called_once_with("color: #d32f2f;")
    assert window._fpga_watchdog_blink_on is False


def test_legacy_keep_connected_settings_do_not_fake_live_connection_state():
    window = MainWindow.__new__(MainWindow)
    window.configuration_helper = {}
    window.plugin_signals = MagicMock()

    window.setGUI_data(
        {"load_firmware_once": True, "keep_fpga_connected": True}
    )

    window.plugin_signals.signal.emit.assert_called_once_with(
        "configurationLoaded"
    )


def test_acquisition_start_failure_restores_controls_and_shows_popup():
    window = MainWindow.__new__(MainWindow)
    window.pispad23_timetagging = SimpleNamespace(active=False)
    window.ui = SimpleNamespace(
        checkBox_pispad23ttmActivate=MagicMock(isChecked=MagicMock(return_value=False)),
        checkBox_ttmActivate=MagicMock(
            isChecked=MagicMock(return_value=False)
        ),
        pushButton_previewStart=MagicMock(),
        pushButton_acquisitionStart=MagicMock(),
        pushButton_stop=MagicMock(),
        pushButton_fpga_connection_cmd=MagicMock(),
        label_FPGA_status=MagicMock(),
        statusBar=MagicMock(),
    )
    window.mcs_manager = MagicMock(is_connected=False)
    error = RuntimeError("firmware is incompatible")
    window._prepare_fpga_for_acquisition = MagicMock(side_effect=error)
    window._update_fpga_connection_button = MagicMock()
    window._show_fpga_initialization_error = MagicMock()

    window.beginAcquisition(is_preview=True)

    window.ui.pushButton_previewStart.setEnabled.assert_called_with(True)
    window.ui.pushButton_acquisitionStart.setEnabled.assert_called_with(True)
    window.ui.pushButton_stop.setEnabled.assert_called_with(False)
    window.ui.pushButton_fpga_connection_cmd.setEnabled.assert_called_with(True)
    assert call(False) not in (
        window.ui.pushButton_fpga_connection_cmd.setEnabled.call_args_list
    )
    window._show_fpga_initialization_error.assert_called_once_with(error)
    window.mcs_manager.run.assert_not_called()


def test_window_shutdown_closes_fpga_even_when_quick_reset_fails():
    window = MainWindow.__new__(MainWindow)
    window._shutdown_started = False
    window._shutdown_complete = False
    window.mcs_manager = MagicMock(is_connected=True)
    window.mcs_manager.quick_reset_fpga.side_effect = TimeoutError("not idle")
    window.timerPreviewImg = MagicMock()
    window.ttm_remote_manager = None

    window.shutdown()

    window.mcs_manager.quick_reset_fpga.assert_called_once_with(timeout=5.0)
    window.mcs_manager.stop_preview.assert_called_once_with()
    window.mcs_manager.stop_acquisition.assert_called_once_with()
    window.mcs_manager.stop_fpga.assert_called_once_with()
    assert window._shutdown_complete is True
    assert window.mcs_manager.is_connected is False


def test_window_shutdown_is_idempotent():
    window = MainWindow.__new__(MainWindow)
    window._shutdown_started = False
    window._shutdown_complete = False
    window.mcs_manager = MagicMock(is_connected=False)
    window.timerPreviewImg = MagicMock()
    window.ttm_remote_manager = None

    window.shutdown()
    window.shutdown()

    window.mcs_manager.stop_fpga.assert_called_once_with()


def test_fpga_handle_stop_closes_all_sessions_after_an_error():
    handle = FpgaHandle.__new__(FpgaHandle)
    handle.configuration = {"stop_event": MagicMock()}
    handle.fpga_handle_process = None
    handle.nifpga_obj = MagicMock()
    handle.nifpga_obj.abort.side_effect = RuntimeError("abort failed")
    handle.nifpga_obj2 = MagicMock()
    primary = handle.nifpga_obj
    secondary = handle.nifpga_obj2

    with pytest.raises(RuntimeError, match="shutdown completed with 1 error"):
        handle.stop()

    primary.abort.assert_called_once_with()
    primary.reset.assert_called_once_with()
    primary.close.assert_called_once_with()
    secondary.abort.assert_called_once_with()
    secondary.reset.assert_called_once_with()
    secondary.close.assert_called_once_with()
    assert handle.nifpga_obj is None
    assert handle.nifpga_obj2 is None


def test_disabling_lissajous_restores_unit_frequencies():
    window = MainWindow.__new__(MainWindow)
    omega_x = MagicMock()
    omega_y = MagicMock()
    phase = MagicMock()
    first_position = MagicMock()
    omega_x.blockSignals.return_value = False
    omega_y.blockSignals.return_value = False
    phase.blockSignals.return_value = False
    first_position.blockSignals.return_value = False
    window.updateLissajousMiniPlot = MagicMock()
    window.ui = SimpleNamespace(
        checkBox_lissajous_opencurve=MagicMock(),
        spinBox_lissajous_omega_x=omega_x,
        spinBox_lissajous_omega_y=omega_y,
        spinBox_lissajous_phase_deg=phase,
        spinBox_lissajous_firstposition=first_position,
        checkBox_circular=MagicMock(
            isChecked=MagicMock(return_value=False)
        ),
    )

    window.lissajousModeChanged(False)

    omega_x.setEnabled.assert_called_once_with(False)
    window.ui.checkBox_lissajous_opencurve.setEnabled.assert_called_once_with(
        False
    )
    omega_y.setEnabled.assert_called_once_with(False)
    omega_x.setValue.assert_called_once_with(1)
    omega_y.setValue.assert_called_once_with(1)
    phase.setEnabled.assert_called_once_with(False)
    phase.setValue.assert_called_once_with(0)
    first_position.setEnabled.assert_called_once_with(False)
    first_position.setValue.assert_called_once_with(0)


def test_lissajous_mini_plot_marks_selected_fpga_sample_points():
    window = MainWindow.__new__(MainWindow)
    window.ui = SimpleNamespace(
        checkBox_lissajous=MagicMock(
            isChecked=MagicMock(return_value=True)
        ),
        checkBox_lissajous_opencurve=MagicMock(
            isChecked=MagicMock(return_value=False)
        ),
        spinBox_lissajous_omega_x=MagicMock(
            value=MagicMock(return_value=1)
        ),
        spinBox_lissajous_omega_y=MagicMock(
            value=MagicMock(return_value=1)
        ),
        spinBox_lissajous_phase_deg=MagicMock(
            value=MagicMock(return_value=0)
        ),
        spinBox_lissajous_firstposition=MagicMock(
            value=MagicMock(return_value=0)
        ),
        spinBox_circular_points=MagicMock(
            value=MagicMock(return_value=4)
        ),
    )
    window.lissajous_mini_curve = MagicMock()
    window.lissajous_mini_points = MagicMock()
    window.lissajous_mini_first_point = MagicMock()
    window.lissajous_mini_plot = MagicMock()

    window.updateLissajousMiniPlot()

    point_data = window.lissajous_mini_points.setData.call_args.kwargs
    np.testing.assert_allclose(
        point_data["x"], [1.0, 0.0, -1.0, 0.0], atol=1e-12
    )
    np.testing.assert_allclose(
        point_data["y"], [0.0, 1.0, 0.0, -1.0], atol=1e-12
    )
    first_point = window.lissajous_mini_first_point.setData.call_args.kwargs
    np.testing.assert_allclose(first_point["x"], [1.0], atol=1e-12)
    np.testing.assert_allclose(first_point["y"], [0.0], atol=1e-12)


def test_only_finite_numeric_scalars_can_be_monitored():
    assert MainWindow._is_monitorable_value(3)
    assert MainWindow._is_monitorable_value(np.float64(2.5))
    assert not MainWindow._is_monitorable_value(True)
    assert not MainWindow._is_monitorable_value(np.nan)
    assert not MainWindow._is_monitorable_value([1, 2])


def test_circular_points_replicate_at_each_raster_pixel_center():
    window = MainWindow.__new__(MainWindow)
    window._latest_status_registers = {
        "circular_scan_x_volts": [99.0],
        "circular_scan_y_volts": [99.0],
        "circular_scan_z_volts": [99.0],
    }
    window.configurationFPGA_dict = {
        "circular_scan_x_volts": [1.0, 2.0],
        "circular_scan_y_volts": [3.0, 4.0],
        "circular_scan_z_volts": [5.0, 6.0],
    }
    # The circular overlay must use the geometry of the displayed image, not
    # potentially newer values in the GUI controls.
    window.currentImage_pos = np.asarray([10.0, 20.0, 30.0])
    window.currentImage_size = np.asarray([4.0, 2.0, 0.0])
    window.currentImage_pixels = np.asarray([2, 1, 1])
    window.ui = SimpleNamespace(
        comboBox_view_projection=MagicMock(
            currentText=MagicMock(return_value="xy")
        ),
        spinBox_calib_x=MagicMock(value=MagicMock(return_value=2.0)),
        spinBox_calib_y=MagicMock(value=MagicMock(return_value=3.0)),
        spinBox_calib_z=MagicMock(value=MagicMock(return_value=4.0)),
        spinBox_off_x_um=MagicMock(value=MagicMock(return_value=-500.0)),
        spinBox_off_y_um=MagicMock(value=MagicMock(return_value=-500.0)),
        spinBox_off_z_um=MagicMock(value=MagicMock(return_value=-500.0)),
        spinBox_range_x=MagicMock(value=MagicMock(return_value=900.0)),
        spinBox_range_y=MagicMock(value=MagicMock(return_value=900.0)),
        spinBox_range_z=MagicMock(value=MagicMock(return_value=900.0)),
        spinBox_nx=MagicMock(value=MagicMock(return_value=9)),
        spinBox_ny=MagicMock(value=MagicMock(return_value=9)),
        spinBox_nframe=MagicMock(value=MagicMock(return_value=9)),
        spinBox_circular_points=MagicMock(value=MagicMock(return_value=2)),
        checkBox_lissajous=MagicMock(
            isChecked=MagicMock(return_value=False)
        ),
        checkBox_lissajous_opencurve=MagicMock(
            isChecked=MagicMock(return_value=False)
        ),
        spinBox_lissajous_omega_x=MagicMock(
            value=MagicMock(return_value=1)
        ),
        spinBox_lissajous_omega_y=MagicMock(
            value=MagicMock(return_value=1)
        ),
        spinBox_lissajous_phase_deg=MagicMock(
            value=MagicMock(return_value=0)
        ),
        spinBox_lissajous_firstposition=MagicMock(
            value=MagicMock(return_value=0)
        ),
    )
    window.circular_scan_points = MagicMock()
    window.circular_scan_first_points = MagicMock()
    window.circular_preview_plot_item = MagicMock()

    window.updateCircularPoints()

    call_kwargs = window.circular_scan_points.setData.call_args.kwargs
    np.testing.assert_allclose(call_kwargs["x"], [11.0, 13.0, 13.0, 15.0])
    np.testing.assert_allclose(call_kwargs["y"], [29.0, 32.0, 29.0, 32.0])
    first_points = window.circular_scan_first_points.setData.call_args.kwargs
    np.testing.assert_allclose(first_points["x"], [11.0, 13.0])
    np.testing.assert_allclose(first_points["y"], [29.0, 29.0])


def test_status_update_appends_one_point_to_each_monitored_register():
    window = MainWindow.__new__(MainWindow)
    first_curve = MagicMock()
    second_curve = MagicMock()
    window._monitored_registers = {
        ("Read Conf. FPGA", "debug_scan_fsm_status"): {
            "source_name": "Read Conf. FPGA",
            "register_name": "debug_scan_fsm_status",
            "times": [],
            "values": [],
            "curve": first_curve,
        },
        ("Conf. FPGA dict.", "current_x_index"): {
            "source_name": "Conf. FPGA dict.",
            "register_name": "current_x_index",
            "times": [],
            "values": [],
            "curve": second_curve,
        },
    }

    window._append_monitor_points(
        {
            "Read Conf. FPGA": {"debug_scan_fsm_status": 2},
            "Conf. FPGA dict.": {"current_x_index": 17},
        },
        timestamp=1.25,
    )

    first_trace = window._monitored_registers[
        ("Read Conf. FPGA", "debug_scan_fsm_status")
    ]
    second_trace = window._monitored_registers[
        ("Conf. FPGA dict.", "current_x_index")
    ]
    assert first_trace["times"] == [1.25]
    assert first_trace["values"] == [2.0]
    assert second_trace["times"] == [1.25]
    assert second_trace["values"] == [17.0]
    first_curve.setData.assert_called_once_with([1.25], [2.0])
    second_curve.setData.assert_called_once_with([1.25], [17.0])
