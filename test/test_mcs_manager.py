import os
import sys
# insert root directory into python module search path
sys.path.insert(1, os.getcwd())

import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from brighteyes_mcs.acquisition.detectors.models import (
    DETECTOR_DISABLED,
    DETECTOR_PISPAD23_TT,
    DETECTOR_PISPAD23_TS_UIMG,
    DETECTOR_PISPAD23,
    DETECTOR_SPAD_ARRAY,
    DETECTOR_SPAD_TTM,
    detector_uses_nifpga_control,
    detector_uses_nifpga_fifo,
)
from brighteyes_mcs.acquisition.manager import McsManager

class TestMcsManager(unittest.TestCase):

    def test_timestamp_restart_never_starts_intensity_receiver_or_storage(self):
        for model in (DETECTOR_PISPAD23_TS_UIMG,):
            instance = McsManager()
            instance.set_detector_model(model)
            instance.dim_x, instance.dim_y, instance.dim_z = 3, 2, 1
            instance.fpga_handle = MagicMock()
            instance.read_registers_dict = MagicMock()
            instance.set_do_not_save(True)
            instance.acquisition_storage.start = MagicMock()
            with patch("brighteyes_mcs.acquisition.detectors.pispad23.pipeline.PISPAD23ReceiverProcess") as receiver:
                for _ in range(2):
                    instance.run()
                    self.assertEqual(instance.detector_pipeline.detector_model, model)
                    self.assertIsNone(instance.detector_receiver_process)
                    self.assertIsNone(instance.detector_receiver_queue)
                    self.assertIsNone(instance.data_process)
                    self.assertIsNone(instance.raw_writer_process)
                    instance.fpga_handle.set_list_fifos_to_read_continously.assert_called_with([])
                    if model == DETECTOR_PISPAD23_TS_UIMG:
                        self.assertTrue(instance.preview_process.is_alive())
                        self.assertIn("shared_fingerprint", instance.detector_pipeline.worker.shared_objects)
                    instance.stop_preview()
                    instance.stop_acquisition()
                receiver.assert_not_called()
            instance.acquisition_storage.start.assert_not_called()

    def test_disabled_runs_fpga_without_data_workers_or_storage(self):
        for preview, raw in ((True, False), (False, False), (False, True)):
            with self.subTest(preview=preview, raw=raw):
                instance = McsManager()
                instance.set_detector_model(DETECTOR_DISABLED)
                instance.fpga_handle = MagicMock()
                instance.read_registers_dict = MagicMock()
                instance.set_do_not_save(preview)
                instance.raw_stream_mode = raw
                instance.acquisition_storage.start = MagicMock()

                instance.run()

                instance.fpga_handle.set_list_fifos_to_read_continously.assert_called_once_with([])
                instance.fpga_handle.runfpga.assert_called_once_with()
                instance.acquisition_storage.start.assert_not_called()
                self.assertIsNone(instance.data_process)
                self.assertIsNone(instance.preview_process)
                self.assertIsNone(instance.raw_writer_process)
                self.assertIsNone(instance.detector_receiver_process)
                self.assertIsNone(instance.detector_receiver_queue)
                instance.stop_preview()
                instance.stop_acquisition()

    def test_disabled_keeps_scan_configuration_and_disables_fifo_output(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_DISABLED)
        instance.is_connected = True
        instance.fpga_handle = MagicMock()
        instance.set_registers_dict({
            "max_pixel": 100, "max_line": 200, "max_frame": 3,
            "stream_out_main_enable": True, "stream_out_aux_enable": True,
            "start_command": True,
        })
        for name, value in (
            ("max_pixel", 100), ("max_line", 200), ("max_frame", 3),
            ("stream_out_main_enable", False), ("stream_out_aux_enable", False),
            ("start_command", True),
        ):
            instance.fpga_handle.register_write_checked.assert_any_call(name, value)

    def test_pispad23_keeps_nifpga_control_without_nifpga_fifo_data(self):
        self.assertTrue(detector_uses_nifpga_fifo(DETECTOR_SPAD_ARRAY))
        self.assertTrue(detector_uses_nifpga_control(DETECTOR_SPAD_ARRAY))
        self.assertTrue(detector_uses_nifpga_fifo(DETECTOR_SPAD_TTM))
        self.assertTrue(detector_uses_nifpga_control(DETECTOR_SPAD_TTM))

        self.assertFalse(detector_uses_nifpga_fifo(DETECTOR_PISPAD23))
        self.assertTrue(detector_uses_nifpga_control(DETECTOR_PISPAD23))
        self.assertFalse(detector_uses_nifpga_fifo(DETECTOR_PISPAD23_TT))
        self.assertTrue(detector_uses_nifpga_control(DETECTOR_PISPAD23_TT))

    def test_parse_dfd_metadata_from_bitfile_name_extracts_values(self):
        cycle_mhz, dfd_nbins = McsManager.parse_dfd_metadata_from_bitfile_name(
            "bitfiles/SingleBoard-Digital-PCIe7820R-49CH-40M91.lvbitx"
        )

        self.assertEqual(cycle_mhz, 40)
        self.assertEqual(dfd_nbins, 91)

    def test_parse_dfd_metadata_from_bitfile_name_extracts_nondefault_cycle(self):
        cycle_mhz, dfd_nbins = McsManager.parse_dfd_metadata_from_bitfile_name(
            "bfdades/SgfgsBogsfgsd-Dgsfgital-Pfeqrqe7qre0R-25CH-37M71.lvbitx"
        )

        self.assertEqual(cycle_mhz, 37)
        self.assertEqual(dfd_nbins, 71)

    def test_acquisition_run_sets_acquisition_run_event(self):
        instance = McsManager()
        instance.acquisition_run_event.set = MagicMock()
        instance.acquisition_stop_event.clear = MagicMock()

        instance.acquisition_run()

        instance.acquisition_run_event.set.assert_called()
        instance.acquisition_stop_event.clear.assert_called()

    def test_acquisition_stop_sets_acquisition_stop_event(self):
        instance = McsManager()
        instance.acquisition_stop_event.set = MagicMock()
        instance.acquisition_run_event.clear = MagicMock()

        instance.acquisition_stop()

        instance.acquisition_stop_event.set.assert_called()
        instance.acquisition_run_event.clear.assert_called()

    def test_acquisition_is_done_returns_true_if_done(self):
        instance = McsManager()
        instance.acquisition_done_event.is_set = MagicMock(return_value=True)

        result = instance.acquisition_is_done()

        self.assertTrue(result)

    def test_acquisition_is_almost_done_returns_true_if_almost_done(self):
        instance = McsManager()
        instance.acquisition_almost_done_event.is_set = MagicMock(return_value=True)

        result = instance.acquisition_is_almost_done()

        self.assertTrue(result)

    def test_set_do_not_save_sets_event(self):
        instance = McsManager()
        instance.do_not_save_event.set = MagicMock()
        instance.do_not_save_event.clear = MagicMock()

        instance.set_do_not_save(True)
        instance.do_not_save_event.set.assert_called()

        instance.set_do_not_save(False)
        instance.do_not_save_event.clear.assert_called()

    def test_set_dfd_enable_sets_dfd_enable(self):
        instance = McsManager()

        instance.set_dfd_enable(True)
        self.assertTrue(instance.dfd_enable)

        instance.set_dfd_enable(False)
        self.assertFalse(instance.dfd_enable)

    def test_set_activate_snake_walk_xy_sets_snake_walk_xy(self):
        instance = McsManager()

        instance.set_activate_snake_walk_xy(True)
        self.assertTrue(instance.snake_walk_xy)

        instance.set_activate_snake_walk_xy(False)
        self.assertFalse(instance.snake_walk_xy)

    def test_set_activate_snake_walk_z_sets_snake_walk_z(self):
        instance = McsManager()

        instance.set_activate_snake_walk_z(True)
        self.assertTrue(instance.snake_walk_z)

        instance.set_activate_snake_walk_z(False)
        self.assertFalse(instance.snake_walk_z)

    def test_connect_sets_is_connected(self):
        instance = McsManager()
        instance.fpga_handle = MagicMock()
        instance.fpga_handle.run = MagicMock()
        instance.update_chuck = MagicMock()

        with patch("brighteyes_mcs.acquisition.manager.FpgaHandle") as MockFpgaHandle:
            MockFpgaHandle.return_value = MagicMock()
            instance.connect()

            self.assertTrue(instance.is_connected)
            instance.fpga_handle.run.assert_called()
            instance.fpga_handle.runfpga.assert_called_once_with()
            instance.update_chuck.assert_called()

    def test_connect_pispad23_disables_nifpga_fifos(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23)
        instance.update_chuck = MagicMock()

        with patch("brighteyes_mcs.acquisition.manager.FpgaHandle") as MockFpgaHandle:
            fpga_handle = MagicMock()
            MockFpgaHandle.return_value = fpga_handle
            instance.connect(
                {
                    "stream_out_main_enable": True,
                    "stream_out_aux_enable": True,
                    "dfd_enable": True,
                },
                list_fifos=["stream_out_main", "stream_out_aux"],
            )

        self.assertEqual(MockFpgaHandle.call_args.kwargs["list_fifos"], [])
        run_registers = fpga_handle.run.call_args.args[0]
        self.assertFalse(run_registers["stream_out_main_enable"])
        self.assertFalse(run_registers["stream_out_aux_enable"])
        self.assertFalse(run_registers["dfd_enable"])

    def test_connect_pispad23_offsets_nifpga_scan_dimensions(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23)
        instance.update_chuck = MagicMock()

        with patch("brighteyes_mcs.acquisition.manager.FpgaHandle") as MockFpgaHandle:
            fpga_handle = MagicMock()
            MockFpgaHandle.return_value = fpga_handle
            instance.connect(
                {
                    "max_pixel": 100,
                    "max_line": 200,
                    "max_frame": 3,
                }
            )

        run_registers = fpga_handle.run.call_args.args[0]
        self.assertEqual(run_registers["max_pixel"], 101)
        self.assertEqual(run_registers["max_line"], 201)
        self.assertEqual(run_registers["max_frame"], 4)

    def test_connect_pispad23tt_offsets_nifpga_scan_dimensions(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23_TT)
        instance.update_chuck = MagicMock()

        with patch("brighteyes_mcs.acquisition.manager.FpgaHandle") as MockFpgaHandle:
            fpga_handle = MagicMock()
            MockFpgaHandle.return_value = fpga_handle
            instance.connect(
                {
                    "max_pixel": 100,
                    "max_line": 200,
                    "max_frame": 3,
                }
            )

        run_registers = fpga_handle.run.call_args.args[0]
        self.assertEqual(run_registers["max_pixel"], 101)
        self.assertEqual(run_registers["max_line"], 201)
        self.assertEqual(run_registers["max_frame"], 4)

    def test_set_registers_dict_pispad23_forces_fifo_registers_off(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23)
        instance.is_connected = True
        instance.fpga_handle = MagicMock()

        instance.set_registers_dict(
            {
                "stream_out_main_enable": True,
                "stream_out_aux_enable": True,
                "dfd_enable": True,
            }
        )

        instance.fpga_handle.register_write_checked.assert_any_call("stream_out_main_enable", False)
        instance.fpga_handle.register_write_checked.assert_any_call("stream_out_aux_enable", False)
        instance.fpga_handle.register_write_checked.assert_any_call("dfd_enable", False)

    def test_set_registers_dict_pispad23_offsets_nifpga_scan_dimensions_only(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23)
        instance.is_connected = True
        instance.fpga_handle = MagicMock()

        instance.set_registers_dict(
            {
                "max_pixel": 100,
                "max_line": 200,
                "max_frame": 3,
            }
        )

        instance.fpga_handle.register_write_checked.assert_any_call("max_pixel", 101)
        instance.fpga_handle.register_write_checked.assert_any_call("max_line", 201)
        instance.fpga_handle.register_write_checked.assert_any_call("max_frame", 4)
        self.assertEqual(instance.registers_configuration["max_pixel"], 100)
        self.assertEqual(instance.registers_configuration["max_line"], 200)
        self.assertEqual(instance.registers_configuration["max_frame"], 3)

    def test_read_registers_dict_pispad23_restores_logical_scan_dimensions(self):
        instance = McsManager()
        instance.set_detector_model(DETECTOR_PISPAD23)
        instance.is_connected = True
        instance.fpga_handle = MagicMock()
        instance.fpga_handle.register_read_all.return_value = {
            "max_time_bins_per_pixel": 10,
            "max_circular_repetition": 1,
            "max_circular_point": 1,
            "time_bin_dwell_cycles": 40,
            "max_pixel": 101,
            "max_line": 201,
            "max_frame": 4,
            "max_repetition": 2,
        }

        instance.read_registers_dict()

        self.assertEqual(instance.dim_x, 100)
        self.assertEqual(instance.dim_y, 200)
        self.assertEqual(instance.dim_z, 3)
        self.assertEqual(instance.registers_configuration["max_pixel"], 100)
        self.assertEqual(instance.registers_configuration["max_line"], 200)
        self.assertEqual(instance.registers_configuration["max_frame"], 3)

    def test_connect_raises_exception_on_error(self):
        instance = McsManager()
        with patch("brighteyes_mcs.acquisition.manager.FpgaHandle") as MockFpgaHandle:
            MockFpgaHandle.return_value = MagicMock()
            MockFpgaHandle.return_value.run = MagicMock(side_effect=Exception("Error"))

            with self.assertRaises(Exception):
                instance.connect()

    def test_run_starts_dataProcess_and_previewProcess(self):
        instance = McsManager()
        instance.fpga_handle = MagicMock()
        instance.read_registers_dict = MagicMock()
        instance.data_process = MagicMock()
        instance.preview_process = MagicMock()
        instance.do_not_save_event.is_set = MagicMock(return_value=True)
        fake_pipeline = MagicMock()
        fake_pipeline.make_receiver_queue.return_value = MagicMock()
        fake_pipeline.make_receiver_process.return_value = None
        fake_pipeline.make_data_preprocess.return_value = instance.data_process
        fake_pipeline.make_acquisition_loop.return_value = instance.preview_process
        instance.detector_pipeline = fake_pipeline

        with patch("brighteyes_mcs.acquisition.manager.create_detector_pipeline", return_value=fake_pipeline):
            instance.run()

        instance.data_process.start.assert_called()
        instance.preview_process.start.assert_called()

    def test_stopAcquisition_stops_dataProcess(self):
        instance = McsManager()
        instance.data_process = MagicMock()

        instance.stop_acquisition()

        instance.data_process.stop.assert_called()

    def test_stop_acquisition_keeps_fpga_session_open(self):
        """Leave the FPGA session open when the acquisition workers stop."""
        instance = McsManager()
        instance.is_connected = True

        instance.stop_acquisition()

        self.assertTrue(instance.is_connected)

    def test_stop_fpga_marks_session_closed_after_an_error(self):
        """Mark the session closed even when closing the FPGA reports an error."""
        instance = McsManager()
        instance.is_connected = True
        instance.fpga_handle = MagicMock()
        instance.fpga_handle.stop.side_effect = RuntimeError("abort failed")

        with self.assertRaises(RuntimeError):
            instance.stop_fpga()

        self.assertFalse(instance.is_connected)

    def test_stopPreview_stops_previewProcess(self):
        instance = McsManager()
        instance.preview_process = MagicMock()

        instance.stop_preview()

        instance.preview_process.stop.assert_called()
        instance.preview_process.join.assert_called()

    def test_getPreviewImage_returns_correct_array(self):
        instance = McsManager()
        instance.shared_image_xy = MagicMock()
        instance.shared_image_xy.get_numpy_handle = MagicMock(return_value=np.array([[1, 2], [3, 4]]))
        instance.shared_image_xy.get_lock = MagicMock()

        result = instance.get_preview_image()

        self.assertTrue((result == np.array([[1, 2], [3, 4]])).all())

    def test_getTrace_in_dfd_mode_returns_counts_per_second(self):
        with patch("brighteyes_mcs.acquisition.manager.mp.Manager", return_value=MagicMock()):
            instance = McsManager()
        instance.dfd_enable = True
        instance.time_resolution = 2.0
        instance.clk_multiplier = 2
        instance.timebins_per_pixel = 8
        instance.trace_sample_per_bins = 5
        instance.expected_words_data_per_frame_digital = 80
        instance.trace_pos = MagicMock(value=0)
        instance.loc_previewed = {"stream_out_main": MagicMock(value=10)}
        instance.shared_trace = MagicMock()
        instance.shared_trace.get_numpy_handle = MagicMock(
            return_value=np.array(
                [
                    [0.0, 1.0, 2.0, 3.0],
                    [10.0, 20.0, 30.0, 40.0],
                ]
            )
        )
        instance.shared_trace_dfd = MagicMock()
        instance.shared_trace_dfd.get_numpy_handle = MagicMock(
            return_value=np.array(
                [
                    [0.0, 1.0, 2.0, 3.0],
                    [4.0, 8.0, 12.0, 16.0],
                    [20.0, 40.0, 60.0, 80.0],
                ]
            )
        )

        trace, trace_pos = instance.get_trace()
        dfd_trace = instance.get_dfd_trace()

        self.assertEqual(trace_pos, 0)
        np.testing.assert_allclose(trace[0], np.array([0.0, 10e-6, 20e-6, 30e-6]))
        np.testing.assert_allclose(
            trace[1],
            np.array([1.0e6, 2.0e6, 3.0e6, 4.0e6]),
        )

        np.testing.assert_allclose(dfd_trace[0], np.array([0.0, 1.0, 2.0, 3.0]))
        np.testing.assert_allclose(
            dfd_trace[1],
            np.array([1.0e6, 2.0e6, 3.0e6, 4.0e6]),
        )
        np.testing.assert_allclose(
            dfd_trace[2],
            np.array([20.0 / (12e-6), 40.0 / (12e-6), 60.0 / (8e-6), 80.0 / (8e-6)]),
        )


if __name__ == '__main__':
    unittest.main()
