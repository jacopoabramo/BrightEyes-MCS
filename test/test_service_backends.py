"""Pin how the mcs service reads and writes registers through each backend."""

import asyncio
import threading
from collections import defaultdict
from typing import Any
from unittest.mock import MagicMock, patch

import nifpga

from brighteyes_mcs.acquisition.detectors.models import DETECTOR_PISPAD23
from brighteyes_mcs.acquisition.manager import McsManager
from brighteyes_mcs.hardware.fpga import FpgaHandle
from brighteyes_mcs.services.backends import DictRegisters, ManagerRegisters
from brighteyes_mcs.services.registers import RegisterSpec, register_specs
from test.fake_bitfile import fake_bitfile_xml


class Register:
    """Stand-in for an nifpga register holding the last value written."""

    def __init__(self) -> None:
        self.value: Any = None

    def write(self, value: Any) -> None:
        self.value = value

    def read(self) -> Any:
        return self.value


class Session:
    """Stand-in for an nifpga session whose registers are created on first use."""

    def __init__(self) -> None:
        self.registers: defaultdict[str, Register] = defaultdict(Register)


def fake_specs() -> list[RegisterSpec]:
    """Return the specs of the fake bitfile."""
    return register_specs(nifpga.Bitfile(fake_bitfile_xml(), parse_contents=True), {})


def connected_manager() -> McsManager:
    """Return a manager for the PISPAD23 detector, connected to a stand-in session."""
    with patch("brighteyes_mcs.acquisition.manager.mp.Manager"):
        manager = McsManager()
    with patch("brighteyes_mcs.hardware.fpga.psutil"):
        handle = FpgaHandle("bitfile", "RIO0", MagicMock(), detector_model=DETECTOR_PISPAD23)
    handle.nifpga_obj = Session()
    manager.set_detector_model(DETECTOR_PISPAD23)
    manager.is_connected = True
    manager.fpga_handle = handle
    return manager


def test_dict_registers_start_from_zero_and_the_defaults() -> None:
    """Start each register from its type's initial value, overlaid by the defaults it names."""
    values = DictRegisters(fake_specs(), {"max_pixel": 64, "not_a_register": 1}).values

    assert values["max_pixel"] == 64
    assert values["current_x_index"] == 0
    assert values["start_command"] is False
    assert "not_a_register" not in values


def test_dict_registers_store_writes_and_notify() -> None:
    """Store a written value, read it back and notify the write listener."""
    backend = DictRegisters(fake_specs(), {})
    names: list[str] = []
    backend.on_write(names.append)

    asyncio.run(backend.write("max_pixel", 7))

    assert asyncio.run(backend.read(["max_pixel"])) == {"max_pixel": 7}
    assert names == ["max_pixel"]


def test_manager_registers_write_through_the_manager_rules() -> None:
    """Apply the manager's rules to a write, such as keeping the main stream off for PISPAD23."""
    backend = ManagerRegisters(connected_manager())

    asyncio.run(backend.write("stream_out_main_enable", True))

    assert asyncio.run(backend.read(["stream_out_main_enable"])) == {
        "stream_out_main_enable": False
    }


def test_manager_registers_read_back_the_written_dimensions() -> None:
    """Read back the dimension written, undoing the offset the manager adds for PISPAD23."""
    manager = connected_manager()
    backend = ManagerRegisters(manager)

    asyncio.run(backend.write("max_pixel", 64))

    assert asyncio.run(backend.read(["max_pixel"])) == {"max_pixel": 64}


def test_manager_registers_skip_a_read_while_the_board_is_busy() -> None:
    """Return no values, without waiting, while another thread holds the board."""
    manager = connected_manager()
    backend = ManagerRegisters(manager)
    held = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with manager.fpga_access():
            held.set()
            release.wait()

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait()
    try:
        assert asyncio.run(backend.read(["max_pixel"])) is None
    finally:
        release.set()
        holder.join()


def test_manager_registers_listen_on_the_handle() -> None:
    """Notify a write listener of every register the manager writes."""
    backend = ManagerRegisters(connected_manager())
    names: list[str] = []
    backend.on_write(names.append)

    asyncio.run(backend.write("max_pixel", 64))

    assert names == ["max_pixel"]
