import os
import sys
# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import unittest
from unittest.mock import MagicMock, call, patch
from types import SimpleNamespace
from PySide6.QtCore import Qt

from brighteyes_mcs.ui.qt.main_window import MainWindow
from brighteyes_mcs.ui.qt.flim_image_view import (
    auxiliary_modifier_selects_navigation,
    control_modifier_selects_navigation,
)

class TestMyClass(unittest.TestCase):

    def test_idle_eta_tracks_clock_and_configuration(self):
        from datetime import datetime

        label = MagicMock()
        instance = SimpleNamespace(
            started_normal=False,
            started_preview=False,
            _expected_duration_seconds=20,
            ui=SimpleNamespace(label_ETA=label),
        )
        with patch("brighteyes_mcs.ui.qt.main_window.datetime") as clock:
            clock.now.return_value = datetime(2026, 9, 24, 23, 59, 50)
            MainWindow.update_idle_eta(instance)
            label.setText.assert_called_with("26/09/25 00:00:10")
            clock.now.return_value = datetime(2026, 9, 24, 23, 59, 51)
            MainWindow.update_idle_eta(instance)
            label.setText.assert_called_with("26/09/25 00:00:11")
            instance._expected_duration_seconds = 60
            MainWindow.update_idle_eta(instance)
            label.setText.assert_called_with("26/09/25 00:00:51")

    def test_idle_eta_does_not_overwrite_preview_or_acquisition(self):
        for acquiring, previewing in ((True, False), (False, True)):
            with self.subTest(acquiring=acquiring, previewing=previewing):
                label = MagicMock()
                instance = SimpleNamespace(
                    started_normal=acquiring,
                    started_preview=previewing,
                    _expected_duration_seconds=20,
                    ui=SimpleNamespace(label_ETA=label),
                )
                MainWindow.update_idle_eta(instance)
                label.setText.assert_not_called()

    def test_configuration_without_arguments_still_emits_loaded(self):
        instance = SimpleNamespace(plugin_signals=SimpleNamespace(signal=MagicMock()))
        MainWindow.setGUI_data(instance)
        MainWindow.setGUI_data(instance)
        self.assertEqual(instance.plugin_signals.signal.emit.call_count, 2)
        instance.plugin_signals.signal.emit.assert_called_with("configurationLoaded")

    def test_configuration_text_accessors_keep_widget_fallbacks(self):
        widget = SimpleNamespace(text=lambda: "scan")
        instance = SimpleNamespace(configuration_helper={
            "name": ("Name", str, widget, True),
        })
        self.assertEqual(MainWindow.getGUI_data(instance), {"name": "scan"})

    def test_failed_laser_preview_does_not_use_an_undefined_response(self):
        import requests

        ui = MagicMock()
        ui.lineEdit_uttm_addr.text.return_value = "localhost:8000"
        instance = SimpleNamespace(ui=ui)
        with patch("brighteyes_mcs.ui.qt.main_window.pg.PlotWidget"), patch(
            "brighteyes_mcs.ui.qt.main_window.requests.get",
            side_effect=requests.ConnectionError("offline"),
        ):
            MainWindow.pushButton_uttm_check_laser_clicked(instance)
        ui.label_uttm_laser_freq.setText.assert_not_called()

    def test_failed_fingerprint_analysis_keeps_previous_statistics(self):
        import numpy as np

        instance = SimpleNamespace(
            fingerprint_markers_centroid=MagicMock(),
            ui=SimpleNamespace(label_dummy=MagicMock()),
        )
        with patch(
            "brighteyes_mcs.ui.qt.main_window.np.linalg.eig",
            side_effect=np.linalg.LinAlgError("no convergence"),
        ):
            MainWindow.microimage_analysis(instance, np.ones((5, 5)))
        instance.ui.label_dummy.setText.assert_not_called()

    def test_auxiliary_position_updates_selected_analog_outputs(self):
        class ValueControl:
            def __init__(self, value):
                self._value = value
                self._signals_blocked = False

            def value(self):
                return self._value

            def setValue(self, value):
                self._value = value

            def blockSignals(self, blocked):
                previous = self._signals_blocked
                self._signals_blocked = blocked
                return previous

        def selector(text):
            return SimpleNamespace(currentText=lambda: text)

        ui = SimpleNamespace(
            spinBox_off_x2_um=ValueControl(30.0),
            spinBox_off_y2_um=ValueControl(8.0),
            spinBox_off_z2_um=ValueControl(-12.0),
            spinBox_calib_x_2=ValueControl(2.0),
            spinBox_calib_y_2=ValueControl(4.0),
            spinBox_calib_z_2=ValueControl(2.0),
            spinBox_offExtra_x_V_2=ValueControl(1.0),
            spinBox_offExtra_y_V_2=ValueControl(-0.5),
            spinBox_offExtra_z_V_2=ValueControl(0.0),
            spinBox_min_x_V_2=ValueControl(-10.0),
            spinBox_max_x_V_2=ValueControl(10.0),
            spinBox_min_y_V_2=ValueControl(-10.0),
            spinBox_max_y_V_2=ValueControl(10.0),
            spinBox_min_z_V_2=ValueControl(-5.0),
            spinBox_max_z_V_2=ValueControl(5.0),
            label_off_x_V_2=MagicMock(),
            label_off_y_V_2=MagicMock(),
            label_off_z_V_2=MagicMock(),
            comboBox_AnalogOut={
                channel: selector(text)
                for channel, text in enumerate(
                    ("X2", "Y2", "X2", "Constant", "Z2", "X", "Y", "Z")
                )
            },
            spinBox_AnalogOut={channel: ValueControl(0.0) for channel in range(8)},
        )
        instance = SimpleNamespace(ui=ui, setRegistersDict=MagicMock())
        instance._auxiliary_axes = lambda: MainWindow._auxiliary_axes(instance)
        instance._auxiliary_axis_voltages = lambda: MainWindow._auxiliary_axis_voltages(instance)
        instance._sync_auxiliary_position_outputs = lambda: MainWindow._sync_auxiliary_position_outputs(instance)

        MainWindow.auxiliaryPositionChanged(instance)

        # X2 is 30/2+1 = 16 V and is constrained to +10 V.
        self.assertEqual(ui.spinBox_AnalogOut[0].value(), 10.0)
        self.assertEqual(ui.spinBox_AnalogOut[2].value(), 10.0)
        self.assertEqual(ui.spinBox_AnalogOut[1].value(), 1.5)
        self.assertEqual(ui.spinBox_AnalogOut[4].value(), -5.0)
        instance.setRegistersDict.assert_called_once_with(
            {
                "analog_output_0_dc_volts": 10.0,
                "analog_output_1_dc_volts": 1.5,
                "analog_output_2_dc_volts": 10.0,
                "analog_output_4_dc_volts": -5.0,
            }
        )
        ui.label_off_x_V_2.setText.assert_called_once_with("10.000000")
        ui.label_off_y_V_2.setText.assert_called_once_with("1.500000")
        ui.label_off_z_V_2.setText.assert_called_once_with("-5.000000")

    def test_central_tabs_are_inserted_before_about(self):
        about_widget = object()
        plugin_widget = object()
        tab_widget = MagicMock()
        tab_widget.indexOf.return_value = 7
        tab_widget.insertTab.return_value = 7
        instance = SimpleNamespace(
            ui=SimpleNamespace(tabWidget=tab_widget),
            about_widget=about_widget,
        )

        result = MainWindow.addCentralTab(instance, plugin_widget, "Plugin")

        tab_widget.insertTab.assert_called_once_with(7, plugin_widget, "Plugin")
        tab_widget.addTab.assert_not_called()
        self.assertEqual(result, 7)

    def test_preview_ctrl_modifier_selects_navigation_by_default(self):
        self.assertTrue(
            control_modifier_selects_navigation(
                Qt.KeyboardModifier.ControlModifier
            )
        )
        self.assertFalse(
            control_modifier_selects_navigation(
                Qt.KeyboardModifier.NoModifier
            )
        )

    def test_preview_ctrl_modifier_can_be_inverted(self):
        self.assertFalse(
            control_modifier_selects_navigation(
                Qt.KeyboardModifier.ControlModifier,
                inverted=True,
            )
        )
        self.assertTrue(
            control_modifier_selects_navigation(
                Qt.KeyboardModifier.NoModifier,
                inverted=True,
            )
        )

    def test_preview_grid_can_be_moved_above_or_below_image(self):
        axes = {"left": MagicMock(), "bottom": MagicMock()}
        instance = SimpleNamespace(
            im_widget=SimpleNamespace(
                getView=lambda: SimpleNamespace(getAxis=lambda name: axes[name])
            )
        )

        MainWindow.previewGridOverImageChanged(instance, True)
        axes["left"].setZValue.assert_called_once_with(1.0)
        axes["bottom"].setZValue.assert_called_once_with(1.0)

        axes["left"].reset_mock()
        axes["bottom"].reset_mock()
        MainWindow.previewGridOverImageChanged(instance, False)
        axes["left"].setZValue.assert_called_once_with(-1.0)
        axes["bottom"].setZValue.assert_called_once_with(-1.0)

    def test_ctrl_shift_selects_auxiliary_preview_drag(self):
        self.assertTrue(
            auxiliary_modifier_selects_navigation(
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier
            )
        )
        self.assertFalse(
            auxiliary_modifier_selects_navigation(
                Qt.KeyboardModifier.ControlModifier
            )
        )
        self.assertFalse(
            auxiliary_modifier_selects_navigation(
                Qt.KeyboardModifier.ShiftModifier
            )
        )

    def test_auxiliary_preview_drag_uses_projection_axes(self):
        class ValueControl:
            def __init__(self, value):
                self._value = value
                self._signals_blocked = False

            def value(self):
                return self._value

            def setValue(self, value):
                self._value = value

            def blockSignals(self, blocked):
                previous = self._signals_blocked
                self._signals_blocked = blocked
                return previous

        expected = {
            "xy": (5.0, 7.0, 3.0),
            "zy": (1.0, 7.0, 7.0),
            "xz": (5.0, 2.0, 8.0),
            "yx": (6.0, 6.0, 3.0),
            "yz": (1.0, 6.0, 8.0),
            "zx": (6.0, 2.0, 7.0),
        }
        for projection, expected_values in expected.items():
            controls = [ValueControl(1.0), ValueControl(2.0), ValueControl(3.0)]
            instance = SimpleNamespace(
                ui=SimpleNamespace(
                    comboBox_view_projection=SimpleNamespace(
                        currentText=lambda projection=projection: projection
                    ),
                    spinBox_off_x2_um=controls[0],
                    spinBox_off_y2_um=controls[1],
                    spinBox_off_z2_um=controls[2],
                ),
                AUXILIARY_PROJECTION_AXES=MainWindow.AUXILIARY_PROJECTION_AXES,
                _sync_auxiliary_position_outputs=MagicMock(
                    return_value={"analog_output_0_dc_volts": 1.0}
                ),
                _auxiliary_drag_write_timer=MagicMock(
                    isActive=MagicMock(return_value=False)
                ),
                setRegistersDict=MagicMock(),
            )

            MainWindow.auxiliaryPreviewDrag(instance, 4.0, 5.0, False)

            self.assertEqual(tuple(control.value() for control in controls), expected_values)
            instance._sync_auxiliary_position_outputs.assert_called_once_with()
            instance._auxiliary_drag_write_timer.start.assert_called_once_with()
            instance.setRegistersDict.assert_not_called()

    def test_auxiliary_preview_drag_flushes_final_value(self):
        controls = []
        for value in (1.0, 2.0, 3.0):
            control = MagicMock()
            control.value.return_value = value
            controls.append(control)

        registers = {"analog_output_0_dc_volts": 4.0}
        instance = SimpleNamespace(
            ui=SimpleNamespace(
                comboBox_view_projection=SimpleNamespace(currentText=lambda: "xy"),
                spinBox_off_x2_um=controls[0],
                spinBox_off_y2_um=controls[1],
                spinBox_off_z2_um=controls[2],
            ),
            AUXILIARY_PROJECTION_AXES=MainWindow.AUXILIARY_PROJECTION_AXES,
            _sync_auxiliary_position_outputs=MagicMock(return_value=registers),
            _auxiliary_drag_write_timer=MagicMock(),
            setRegistersDict=MagicMock(),
        )

        MainWindow.auxiliaryPreviewDrag(instance, 0.0, 0.0, True)

        instance._auxiliary_drag_write_timer.stop.assert_called_once_with()
        instance.setRegistersDict.assert_called_once_with(registers)

    @staticmethod
    def _preview_click_fixture(modifiers, inverted=False):
        point = SimpleNamespace(x=lambda: 1.25, y=lambda: 2.5)
        event = SimpleNamespace(
            double=lambda: True,
            pos=lambda: object(),
            modifiers=lambda: modifiers,
        )
        spin_x = MagicMock()
        spin_y = MagicMock()
        spin_z = MagicMock()
        spin_z.value.return_value = 3.75
        instance = SimpleNamespace(
            im_widget=SimpleNamespace(
                view=SimpleNamespace(
                    vb=SimpleNamespace(mapToView=lambda _point: point)
                )
            ),
            preview_view_box=SimpleNamespace(
                navigation_allowed=lambda value:
                    control_modifier_selects_navigation(value, inverted)
            ),
            ui=SimpleNamespace(
                comboBox_view_projection=SimpleNamespace(
                    currentText=lambda: "xy"
                ),
                spinBox_off_x_um=spin_x,
                spinBox_off_y_um=spin_y,
                spinBox_off_z_um=spin_z,
            ),
            getGUI_data=MagicMock(return_value={}),
            markers_list=[],
            drawMarkers=MagicMock(),
            markersViewTable=MagicMock(),
            offset_um_Changed=MagicMock(),
        )
        return instance, event

    def test_unmodified_double_click_adds_preview_marker_by_default(self):
        instance, event = self._preview_click_fixture(
            Qt.KeyboardModifier.NoModifier
        )

        MainWindow.imageClicked(instance, event)

        self.assertEqual(
            instance.markers_list,
            [{
                "offset_x_um": 1.25,
                "offset_y_um": 2.5,
                "offset_z_um": 3.75,
            }],
        )
        instance.offset_um_Changed.assert_not_called()

    def test_ctrl_double_click_moves_preview_by_default(self):
        instance, event = self._preview_click_fixture(
            Qt.KeyboardModifier.ControlModifier
        )

        MainWindow.imageClicked(instance, event)

        self.assertEqual(instance.markers_list, [])
        instance.ui.spinBox_off_x_um.setValue.assert_called_once_with(1.25)
        instance.ui.spinBox_off_y_um.setValue.assert_called_once_with(2.5)
        instance.ui.spinBox_off_z_um.setValue.assert_called_once_with(3.75)
        instance.offset_um_Changed.assert_called_once_with()

    def test_laser_force_pulsing_applies_and_restores_registers(self):
        instance = SimpleNamespace(
            configurationFPGA_dict={
                "laser_time_bin_mode_enable": False,
                "max_laser_time_bin": 9,
            },
            mcs_manager=SimpleNamespace(
                registers_configuration={},
                default_configuration={},
            ),
            ui=SimpleNamespace(
                checkBox_DFD=SimpleNamespace(isChecked=lambda: False),
            ),
            _laser_force_pulsing_previous=None,
            setRegistersDict=MagicMock(),
        )
        instance._currentLaserRegisterValue = (
            lambda name: MainWindow._currentLaserRegisterValue(instance, name)
        )

        MainWindow.laserForcePulsingChanged(instance, True)
        instance.setRegistersDict.assert_called_once_with(
            {
                "laser_time_bin_mode_enable": True,
                "max_laser_time_bin": 1,
                "laser_force_pulsing_enable": True,
            }
        )

        instance.setRegistersDict.reset_mock()
        MainWindow.laserForcePulsingChanged(instance, False)
        instance.setRegistersDict.assert_called_once_with(
            {
                "laser_time_bin_mode_enable": False,
                "max_laser_time_bin": 9,
                "laser_force_pulsing_enable": False,
            }
        )
        self.assertIsNone(instance._laser_force_pulsing_previous)

    def test_dfd_disables_and_unchecks_force_pulsing(self):
        force_pulsing = MagicMock()
        force_pulsing.isChecked.return_value = True
        instance = SimpleNamespace(
            ui=SimpleNamespace(
                checkBox_DFD=SimpleNamespace(isChecked=lambda: True),
                checkBox_pulsing_forced=force_pulsing,
            )
        )

        MainWindow.updateLaserForcePulsingAvailability(instance)

        force_pulsing.setChecked.assert_called_once_with(False)
        force_pulsing.setEnabled.assert_called_once_with(False)

    @staticmethod
    def _auto_lifetime_fixture(channel="LIFETIME_HSV"):
        instance = SimpleNamespace(
            started_normal=False,
            started_preview=True,
            raw_stream_mode=False,
            _auto_lifetime_correction_pending=True,
            _auto_lifetime_correction_completed=False,
            ui=SimpleNamespace(
                checkBox_DFD=SimpleNamespace(isChecked=lambda: True),
                comboBox_plot_channel=SimpleNamespace(
                    currentText=lambda: channel
                ),
            ),
            colorLifetimeDeltaTauUseHistogramMean=MagicMock(
                return_value=True
            ),
        )
        instance._syncAutoLifetimeCorrectionWithPlotSelection = (
            lambda: MainWindow._syncAutoLifetimeCorrectionWithPlotSelection(
                instance
            )
        )
        return instance

    def test_auto_lifetime_correction_waits_for_twenty_percent(self):
        instance = self._auto_lifetime_fixture()

        result_before = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 19, 100
        )
        result_at_threshold = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 20, 100
        )

        self.assertFalse(result_before)
        self.assertTrue(result_at_threshold)
        instance.colorLifetimeDeltaTauUseHistogramMean.assert_called_once_with()

    def test_auto_lifetime_correction_retries_until_data_are_valid(self):
        instance = self._auto_lifetime_fixture()
        instance.colorLifetimeDeltaTauUseHistogramMean.side_effect = [False, True]

        first_attempt = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 20, 100
        )
        second_attempt = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 25, 100
        )

        self.assertFalse(first_attempt)
        self.assertTrue(second_attempt)
        self.assertEqual(
            instance.colorLifetimeDeltaTauUseHistogramMean.call_count, 2
        )

    def test_auto_lifetime_correction_only_runs_once(self):
        instance = self._auto_lifetime_fixture()

        def complete_correction():
            instance._auto_lifetime_correction_pending = False
            instance._auto_lifetime_correction_completed = True
            return True

        instance.colorLifetimeDeltaTauUseHistogramMean.side_effect = (
            complete_correction
        )

        first_attempt = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 20, 100
        )
        second_attempt = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 40, 100
        )

        self.assertTrue(first_attempt)
        self.assertFalse(second_attempt)
        instance.colorLifetimeDeltaTauUseHistogramMean.assert_called_once_with()

    def test_auto_lifetime_correction_disarms_outside_hsv(self):
        instance = self._auto_lifetime_fixture(channel="LIFETIME_HSL")

        result = MainWindow._maybeAutoCorrectLifetimeAfterFirstFrameProgress(
            instance, 20, 100
        )

        self.assertFalse(result)
        self.assertFalse(instance._auto_lifetime_correction_pending)
        instance.colorLifetimeDeltaTauUseHistogramMean.assert_not_called()

    def test_circular_view_button_follows_circular_activation(self):
        button = MagicMock()
        instance = SimpleNamespace(
            ui=SimpleNamespace(pushButton_updateCircularView=button)
        )

        MainWindow.updateCircularViewAvailability(instance, False)
        MainWindow.updateCircularViewAvailability(instance, True)

        self.assertEqual(
            button.setEnabled.call_args_list,
            [call(False), call(True)],
        )


if __name__ == '__main__':
    unittest.main()
