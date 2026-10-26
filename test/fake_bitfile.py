"""Build a bitfile for tests: the XML `nifpga.Bitfile` parses, with one register of each kind."""

from pathlib import Path

FXP = (
    "<FXP><Name>{name}</Name><Signed>true</Signed>"
    "<WordLength>20</WordLength><IntegerWordLength>5</IntegerWordLength></FXP>"
)

REGISTERS: tuple[tuple[str, str, bool, bool], ...] = (
    ("start_command", "<Boolean><Name>{name}</Name></Boolean>", False, False),
    ("analog_output_7_source_selector", "<U8><Name>{name}</Name></U8>", False, False),
    ("max_pixel", "<I32><Name>{name}</Name></I32>", False, False),
    ("dfd_dwell_time_cycles_120mhz", "<U32><Name>{name}</Name></U32>", False, False),
    ("wait_post_frame_cycles", "<I64><Name>{name}</Name></I64>", False, False),
    ("spad_configuration_message", "<U64><Name>{name}</Name></U64>", False, False),
    ("current_x_index", "<I32><Name>{name}</Name></I32>", True, False),
    ("analog_output_0_dc_volts", FXP, False, False),
    (
        "axis_start_offset_volts",
        "<Array><Name>{name}</Name><Size>3</Size><Type>" + FXP + "</Type></Array>",
        False,
        False,
    ),
    (
        "digital_outputs",
        "<Array><Name>{name}</Name><Size>4</Size>"
        "<Type><Boolean><Name>{name}</Name></Boolean></Type></Array>",
        False,
        False,
    ),
    ("internal_register", "<I32><Name>{name}</Name></I32>", False, True),
    ("error_text", "<String><Name>{name}</Name></String>", False, False),
    ("Input U64", "<U64><Name>{name}</Name></U64>", False, False),
)
"""Name, datatype XML, whether an indicator, and whether internal, of each register."""


BOOL = "<Boolean><Name>{name}</Name></Boolean>"
I32 = "<I32><Name>{name}</Name></I32>"
I64 = "<I64><Name>{name}</Name></I64>"
U8 = "<U8><Name>{name}</Name></U8>"


def array(length: int, element: str) -> str:
    """Return the datatype XML of an array of `length` elements of type `element`."""
    return f"<Array><Name>{{name}}</Name><Size>{length}</Size><Type>{element}</Type></Array>"


def settings_registers() -> tuple[tuple[str, str, bool, bool], ...]:
    """Return a control of every register the service's settings read or write."""
    kinds: dict[str, str] = {
        "axis_calibration_volts_per_step": array(3, FXP),
        "axis_start_offset_volts": array(3, FXP),
        "laser_excitation_sequence": array(24, U8),
        "analog_a_input_selector": U8,
        "analog_b_input_selector": U8,
        "slave_mode_external_source_selector": U8,
        "tag_clock_duration_cycles": I64,
        "wait_laser_startup_cycles": I64,
        "wait_post_frame_cycles": I64,
    }
    for name in (
        "max_pixel",
        "max_line",
        "max_frame",
        "max_time_bins_per_pixel",
        "time_bin_dwell_cycles",
        "max_circular_point",
        "max_circular_repetition",
    ):
        kinds[name] = I32
    for axis in "xyz":
        kinds[f"circular_scan_{axis}_volts"] = array(32, FXP)
        kinds[f"min_{axis}_volts"] = FXP
        kinds[f"max_{axis}_volts"] = FXP
    for channel in range(8):
        kinds[f"analog_output_{channel}_source_selector"] = U8
        kinds[f"analog_output_{channel}_dc_volts"] = FXP
    for channel in range(4):
        kinds[f"analog_a_channel_{channel}_integrate_enable"] = BOOL
        kinds[f"analog_a_channel_{channel}_invert_enable"] = BOOL
    for number in range(1, 5):
        kinds[f"laser_{number}_enable"] = BOOL
    for name in (
        "circular_scan_enable",
        "xy_snake_scan_enable",
        "z_snake_scan_enable",
        "wait_laser_first_time_only_enable",
        "analog_a_differential_mode_enable",
        "analog_b_differential_mode_enable",
        "detector_49_channel_mode_enable",
        "dummy_data_enable",
        "slave_mode_enable",
        "spad_vr0_enable",
        "spad_vr1_enable",
        "dfd_laser_sync_debug_enable",
        "dfd_enable",
        "stream_out_aux_enable",
        "stream_out_main_enable",
    ):
        kinds[name] = BOOL
    return tuple((name, kind, False, False) for name, kind in kinds.items())


SETTINGS_REGISTERS = settings_registers()
"""A control of every register the service's settings read or write."""


def fake_bitfile_xml(registers: tuple[tuple[str, str, bool, bool], ...] = REGISTERS) -> str:
    """Return the XML of a bitfile holding every register of `registers`."""
    rows = "".join(
        f"<Register><Name>{name}</Name><Indicator>{str(indicator).lower()}</Indicator>"
        f"<Datatype>{datatype.format(name=name)}</Datatype><Offset>0</Offset>"
        f"<Internal>{str(internal).lower()}</Internal>"
        "<AccessMayTimeout>false</AccessMayTimeout></Register>"
        for name, datatype, indicator, internal in registers
    )
    return (
        "<Bitfile><SignatureRegister>0123ABCD</SignatureRegister>"
        "<Project><CompilationResultsTree><CompilationResults><NiFpga>"
        "<BaseAddressOnDevice>0</BaseAddressOnDevice><DmaChannelAllocationList/>"
        "</NiFpga></CompilationResults></CompilationResultsTree></Project>"
        f"<VI><RegisterList>{rows}</RegisterList></VI></Bitfile>"
    )


def write_fake_bitfile(
    directory: Path, registers: tuple[tuple[str, str, bool, bool], ...] = REGISTERS
) -> Path:
    """Write a fake bitfile holding `registers` into `directory` and return its path."""
    path = directory / "fake_bitfile.xml"
    path.write_text(fake_bitfile_xml(registers), encoding="utf-8")
    return path
