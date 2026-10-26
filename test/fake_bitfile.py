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


def fake_bitfile_xml() -> str:
    """Return the XML of a bitfile holding every register of `REGISTERS`."""
    registers = "".join(
        f"<Register><Name>{name}</Name><Indicator>{str(indicator).lower()}</Indicator>"
        f"<Datatype>{datatype.format(name=name)}</Datatype><Offset>0</Offset>"
        f"<Internal>{str(internal).lower()}</Internal>"
        "<AccessMayTimeout>false</AccessMayTimeout></Register>"
        for name, datatype, indicator, internal in REGISTERS
    )
    return (
        "<Bitfile><SignatureRegister>0123ABCD</SignatureRegister>"
        "<Project><CompilationResultsTree><CompilationResults><NiFpga>"
        "<BaseAddressOnDevice>0</BaseAddressOnDevice><DmaChannelAllocationList/>"
        "</NiFpga></CompilationResults></CompilationResultsTree></Project>"
        f"<VI><RegisterList>{registers}</RegisterList></VI></Bitfile>"
    )


def write_fake_bitfile(directory: Path) -> Path:
    """Write the fake bitfile into `directory` and return its path."""
    path = directory / "fake_bitfile.xml"
    path.write_text(fake_bitfile_xml(), encoding="utf-8")
    return path
