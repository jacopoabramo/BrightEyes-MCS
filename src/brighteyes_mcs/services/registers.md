# BrightEyes-MCSLL registers

The mcs service reads this table for the descriptions of the registers it serves.

| Name                           | Type       | Read/Write | Description                                                                                                                                      |
|--------------------------------|------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| **Main**                       |            |            |                                                                                                                                                  |
| start_command | Bool       | RW         | Start the scanning                                                                                                                               |
| stop_command | Bool       | RW         | Stop the scanning                                                                                                                                |
| debug_scan_fsm_status | I16        | R          | Status of the FSM                                                                                                                                |
|                                |            |            |                                                                                                                                                  |
| **Scan Settings**              |            |            |                                                                                                                                                  |
| time_bin_dwell_cycles | I32        | RW         | Wait Cycles per bin in 40MHz clk units (default: 40)                                                                                             |
| max_time_bins_per_pixel | I32        | RW         | Number of timebins per pixel                                                                                                                     |
| max_pixel | I32        | RW         | Number of pixel (X)                                                                                                                              |
| max_line | I32        | RW         | Number of lines (Y)                                                                                                                              |
| max_frame | I32        | RW         | Number of frames (Z)                                                                                                                             |
| max_repetition | I32        | RW         | Number of repetition (REP)                                                                                                                       |
| axis_start_offset_volts | Fxp-Array  | RW         | Array [x,y,z] offset in V                                                                                                                        |
| axis_calibration_volts_per_step | Fxp-Array  | RW         | Array [x,y,z] calibration in V/step                                                                                                              |
| xy_snake_scan_enable | Bool       | RW         | If enabled the scanning is performed as "snake-scanning" else use the normal "raster scanning" (default: False)                                  |
|                                |            |            |                                                                                                                                                  |
| **Analog Output**              |            |            |                                                                                                                                                  |
| (for all channels from 0 to 7) |            |            |                                                                                                                                                  |
| analog_output_7_volts | Fxp        | R          | Current Voltage on AnalogOUT                                                                                                                     |
| analog_output_7_source_selector | U8         | RW         | 0 => X, 1 => Y, 2 => Z, else constant DC value                                                                                                   |
| analog_output_7_dc_volts | Fxp        | RW         | Constant value for Analog Output                                                                                                                 |
|                                |            |            |                                                                                                                                                  |
| **Scanning Status**            |            |            |                                                                                                                                                  |
| current_line_parity_flag | Bool       | R          | Current Parity Line (for snake)                                                                                                                  |
| current_cycle_index | I32        | R          | Current Cycle                                                                                                                                    |
| current_time_bin_index | I32        | R          | Current timebin                                                                                                                                  |
| current_x_index | I32        | R          | Current X                                                                                                                                        |
| current_y_index | I32        | R          | Current Y                                                                                                                                        |
| current_z_index | I32        | R          | Current Z                                                                                                                                        |
| current_repetition_index | I32        | R          | Current Rep                                                                                                                                      |
|                                |            |            |                                                                                                                                                  |
| **Detection Configuration**    |            |            |                                                                                                                                                  |
| wait_initialization_time_in_us | U32        | RW         | SPAD configuration - time to wait before start acquisition                                                                                       |
| spad_configuration_message | U64        | RW         | SPAD configuration message cmd send                                                                                                              |
| spad_configuration_message_length | U8         | RW         | SPAD configuration message length                                                                                                                |
| spad_sdata_invert_enable | Bool       | RW         | SPAD configuration invert the cmd logic (useful for some SPAD prototype)                                                                         |
| tag_clock_duration_cycles | I64        | RW         | SPAD configuration - sync output duration (40 MHz units)                                                                                         |
| detector_fpga_holdoff_cycles | U16        | RW         | holdOff time (FPGA based) in 120 MHz units                                                                                                       |
| dummy_data_enable | Bool       | RW         | If enable produces dummy data instead of using data from the detector                                                                            |
|                                |            |            |                                                                                                                                                  |
| **Laser Control**              |            |            |                                                                                                                                                  |
| wait_laser_startup_cycles | I64        | RW         | Wait after turning on laser (in 40 MHz units)                                                                                                    |
| wait_post_frame_cycles | I64        | RW         | Wait after frame completation (in 40 MHz units)                                                                                                  |
| wait_laser_first_time_only_enable | Bool       | RW         | Wait after turning on laser only the first time                                                                                                  |
| laser_off_after_measurement_enable | Bool       | RW         | If active turn off the laser after a measurement                                                                                                 |
|                                |            |            |                                                                                                                                                  |
| **Circular Scanning Settings** |            |            |                                                                                                                                                  |
| circular_scan_x_volts | Fxp-Array  | RW         | Array of Voltages X for circular scanning                                                                                                        |
| circular_scan_y_volts | Fxp-Array  | RW         | Array of Voltages Y for circular scanning                                                                                                        |
| circular_scan_z_volts | Fxp-Array  | RW         | Array of Voltages Z for circular scanning                                                                                                        |
| circular_scan_enable | Bool       | RW         | If active, use `circular_scan_x_volts` or positions supplied through `stream_in` instead of raster scanning                                      |
|                                |            |            |                                                                                                                                                  |
| **Scanning LImits**            |            |            |                                                                                                                                                  |
| max_x_volts | Fxp        | RW         | Set Voltages Limits Max X Voltage                                                                                                                |
| max_y_volts | Fxp        | RW         | Set Voltages Limits Max Y Voltage                                                                                                                |
| max_z_volts | Fxp        | RW         | Set Voltages Limits Max Z Voltage                                                                                                                |
| min_x_volts | Fxp        | RW         | Set Voltages Limits Min X Voltage                                                                                                                |
| min_y_volts | Fxp        | RW         | Set Voltages Limits Min Y Voltage                                                                                                                |
| min_z_volts | Fxp        | RW         | Set Voltages Limits Min Z Voltage                                                                                                                |
|                                |            |            |                                                                                                                                                  |
| **FIFO Settings**              |            |            |                                                                                                                                                  |
| stream_out_aux_enable | Bool       | RW         | Activate the FIFO Analog                                                                                                                         |
| stream_out_main_enable | Bool       | RW         | Activate the FIFO Digital                                                                                                                        |
| internal_fifo_analog_overflow_flag | Bool       | R          | True when the internal analog FIFO overflows during the scan                                                                                     |
| internal_fifo_spad_overflow_flag | Bool       | R          | True when the internal SPAD FIFO overflows during the scan                                                                                       |
| stream_out_aux_overflow_cycle_counter | U64        | R          | Counter of overflow cycles for `stream_out_aux`                                                                                                  |
| stream_out_main_overflow_cycle_counter | U64        | R          | Counter of overflow cycles for `stream_out_main`                                                                                                 |
|                                |            |            |                                                                                                                                                  |
| **Laser Enable**               |            |            |                                                                                                                                                  |
| laser_1_enable | Bool       | RW         | Laser Enable 1                                                                                                                                   |
| laser_2_enable | Bool       | RW         | Laser Enable 2                                                                                                                                   |
| laser_3_enable | Bool       | RW         | Laser Enable 3                                                                                                                                   |
| laser_4_enable | Bool       | RW         | Laser Enable 4                                                                                                                                   |
|                                |            |            |                                                                                                                                                  |
| **Analog Input**               |            |            |                                                                                                                                                  |
| analog_a_input_selector | U8         | RW         | Select the Analog input for Analog A channel                                                                                                     |
| analog_b_input_selector | U8         | RW         | Select the Analog input for Analog B channel                                                                                                     |
|                                |            |            |                                                                                                                                                  |
| analog_a_differential_mode_enable | Bool       | RW         | True: signal derivative during within the timebin; False: signal direct                                                                          |
| analog_b_differential_mode_enable | Bool       | RW         | True: signal derivative during within the timebin; False: signal direct                                                                          |
|                                |            |            |                                                                                                                                                  |
| (for all channels from 0 to 7) |            |            |                                                                                                                                                  |
| analog_a_channel_7_invert_enable | Bool       | RW         | True: signal inverted; False: signal not inverted                                                                                                |
| analog_a_channel_7_integrate_enable | Bool       | RW         | True: signal integrated; False: signal not integrated. The integration is performed at the max ADC readout speed                                 |
| analog_input_7_volts | Fxp        | R          | Current Voltage on AnalogIN                                                                                                                      |
|                                |            |            |                                                                                                                                                  |
| **Digital Frequency Domain**   |            |            |                                                                                                                                                  |
| L1                             | U8         | RW         | A state of laser sync for DFD - AAA_AAA_BBB_BBB                                                                                                  |
| L2                             | U8         | RW         | B state of laser sync for DFD - AAA_000_BBB_000                                                                                                  |
| L3                             | U8         | RW         | C state of laser sync for DFD - AA0_0BB_00C_C00                                                                                                  |
| L4                             | U8         | RW         | D state of laser sync for DFD - A00_B00_C00_D00                                                                                                  |
| dfd_enable | Bool       | RW         | Activate the DFD                                                                                                                                 |
| dfd_dwell_time_cycles_120mhz | U32        | RW         | Time interval for the transmission of full histogram (in 120MHz units) (Default: 1e6)  <= USUALLY NOT USED                                       |
| dfd_internal_dwell_time_enable | Bool       | RW         | False: use the pixel index parity for triggering the transmission of the DFD histogram; True: use the Dwell time set (Default: False)            |
| dfd_laser_sync_debug_enable | Bool       | RW         | True: the channel 26 become the laser time reference (needed for a proper phasor analysis); False: channel 26 is connected to the channel_extra1 |
| dfd_current_position_index | Fxp        | R          | Status of the DFD current pixel                                                                                                                  |
| dfd_transmitted_position_index | Fxp        | R          | Status of the DFD current pixel transmitted                                                                                                      |
| dfd_acquisition_active_status | Bool       | R          | Status of the DFD module if activated or not                                                                                                     |
| internal_fifo_dfd_overflow_flag | Bool       | R          | Status of the overflow of the internal DFD FIFO                                                                                                  |
|                                |            |            |                                                                                                                                                  |
| **Costum Scanning Position**   |            |            |                                                                                                                                                  |
| custom_positions_last_pixelwise_address | U32        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_last_framewise_address | U32        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_stream_in_ready_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_current_address | U32        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_x_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_y_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_z_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_tx_begin_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_extra_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_update_mode_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_tx_end_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_current_address | U32        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_x_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_y_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_z_volts | Fxp        | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_tx_begin_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_extra_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_update_mode_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
| custom_positions_offset_tx_end_flag | Bool       | R          | Internal use / Debug                                                                                                                             |
|                                |            |            |                                                                                                                                                  |
| **Internal / Debug**           |            |            |                                                                                                                                                  |
| shutter_enable | Bool-Array | RW         | Internal use / Debug                                                                                                                             |
| debug_pixel_tag | Bool       | RW         | Internal use / Debug                                                                                                                             |
| debug_line_tag | Bool       | RW         | Internal use / Debug                                                                                                                             |
| debug_frame_tag | Bool       | RW         | Internal use / Debug                                                                                                                             |
| debug_repetition_tag | Bool       | RW         | Internal use / Debug                                                                                                                             |
| debug_end_of_frame_flag | Bool       | RW         | Internal use / Debug                                                                                                                             |
| debug_line_counter | I64        | RW         | Internal use / Debug                                                                                                                             |
| tag_turnoff_pixel_counter | I64        | R          | Internal use / Debug                                                                                                                             |
| tag_turnoff_line_counter | I64        | R          | Internal use / Debug                                                                                                                             |
| tag_turnoff_frame_counter | I64        | R          | Internal use / Debug                                                                                                                             |
| debug_t | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_x_index | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_y_index | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_z_index | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_x_index_2 | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_y_index_2 | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_z_index_2 | I32        | RW         | Internal use / Debug                                                                                                                             |
| debug_repetition_index | I32        | RW         | Internal use / Debug                                                                                                                             |
