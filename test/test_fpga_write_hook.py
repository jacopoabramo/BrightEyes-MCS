"""Pin that every register write the board accepts reaches the write listeners."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from brighteyes_mcs.acquisition.detectors.models import DETECTOR_SPAD_ARRAY
from brighteyes_mcs.acquisition.manager import DEFAULT_REGISTERS, McsManager
from brighteyes_mcs.hardware.fpga import FpgaHandle


class Register:
    """Stand-in for an nifpga register, recording each value or refusing every write."""

    def __init__(self, written: list[Any], refuse: bool) -> None:
        self.written = written
        self.refuse = refuse

    def write(self, value: Any) -> None:
        if self.refuse:
            raise RuntimeError("write refused")
        self.written.append(value)


class Session:
    """Stand-in for an nifpga session holding one register."""

    def __init__(self, name: str, register: Register) -> None:
        self.registers = {name: register}


@pytest.fixture
def make_handle() -> Callable[[bool], FpgaHandle]:
    """Return a factory for handles whose `max_pixel` register accepts or refuses writes."""

    def make(refuse: bool) -> FpgaHandle:
        with patch("brighteyes_mcs.hardware.fpga.psutil"):
            handle = FpgaHandle("bitfile", "RIO0", MagicMock(), detector_model=DETECTOR_SPAD_ARRAY)
        handle.nifpga_obj = Session("max_pixel", Register([], refuse))
        return handle

    return make


def test_a_successful_write_notifies_listeners(make_handle: Callable[[bool], FpgaHandle]) -> None:
    """Notify each listener with the register name after the board accepts a write."""
    handle = make_handle(False)
    names: list[str] = []
    handle.add_write_listener(names.append)

    handle.register_write_checked("max_pixel", 5)

    assert names == ["max_pixel"]


def test_a_failed_write_notifies_nobody(make_handle: Callable[[bool], FpgaHandle]) -> None:
    """Raise the board's error and notify nobody when a checked write fails."""
    handle = make_handle(True)
    names: list[str] = []
    handle.add_write_listener(names.append)

    with pytest.raises(RuntimeError):
        handle.register_write_checked("max_pixel", 5)

    assert names == []


def test_unchecked_write_notifies_only_on_success(
    make_handle: Callable[[bool], FpgaHandle],
) -> None:
    """Notify after an unchecked write the board accepts, and not after one it refuses."""
    accepting = make_handle(False)
    refusing = make_handle(True)
    names: list[str] = []
    accepting.add_write_listener(names.append)
    refusing.add_write_listener(names.append)

    accepting.register_write("max_pixel", 5)
    refusing.register_write("max_pixel", 5)

    assert names == ["max_pixel"]


def test_default_registers_seed_each_manager() -> None:
    """Give each manager its own copy of the default register values."""
    with patch("brighteyes_mcs.acquisition.manager.mp.Manager"):
        first = McsManager()
        second = McsManager()

    assert first.default_configuration == second.default_configuration == DEFAULT_REGISTERS
    first.default_configuration["max_pixel"] = 3
    assert second.default_configuration["max_pixel"] == DEFAULT_REGISTERS["max_pixel"]
