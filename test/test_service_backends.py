"""Pin how the mcs service reads and writes registers through each backend."""

import asyncio
import threading
import time
from collections import defaultdict
from typing import Any
from unittest.mock import MagicMock, call, patch

import nifpga
import numpy as np
import pytest

from brighteyes_mcs.acquisition.detectors.models import DETECTOR_PISPAD23
from brighteyes_mcs.acquisition.manager import McsManager
from brighteyes_mcs.acquisition.registers import run_registers
from brighteyes_mcs.acquisition.settings import AcquisitionConfig
from brighteyes_mcs.hardware.fpga import FpgaHandle
from brighteyes_mcs.services.backends import DictRegisters, ManagerRegisters, RunStatus
from brighteyes_mcs.services.physical import RunSettings, run_config
from brighteyes_mcs.services.registers import RegisterSpec, register_specs
from test.fake_bitfile import fake_bitfile_xml
from test.test_service_controller import StubBackend
from test.window_settings import settings_of, window_config


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


def test_dict_registers_write_many_stores_and_notifies_in_order() -> None:
    """Store every value of one call and notify each name in order."""
    backend = DictRegisters(fake_specs(), {})
    names: list[str] = []
    backend.on_write(names.append)

    asyncio.run(backend.write_many({"max_pixel": 5, "current_x_index": 2}))

    assert asyncio.run(backend.read(["max_pixel", "current_x_index"])) == {
        "max_pixel": 5,
        "current_x_index": 2,
    }
    assert names == ["max_pixel", "current_x_index"]


def test_manager_registers_write_many_makes_one_manager_call() -> None:
    """Pass all values of one call to the manager in one `set_registers_dict`."""
    manager = MagicMock(spec=McsManager)
    backend = ManagerRegisters(manager)

    asyncio.run(backend.write_many({"max_pixel": 5, "max_line": 6}))

    assert manager.set_registers_dict.call_args_list == [call({"max_pixel": 5, "max_line": 6})]


def test_manager_registers_write_through_the_manager_rules() -> None:
    """Apply the manager's rules to a write, such as keeping the main stream off for PISPAD23."""
    backend = ManagerRegisters(connected_manager())

    asyncio.run(backend.write_many({"stream_out_main_enable": True}))

    assert asyncio.run(backend.read(["stream_out_main_enable"])) == {
        "stream_out_main_enable": False
    }


def test_manager_registers_read_back_the_written_dimensions() -> None:
    """Read back the dimension written, undoing the offset the manager adds for PISPAD23."""
    manager = connected_manager()
    backend = ManagerRegisters(manager)

    asyncio.run(backend.write_many({"max_pixel": 64}))

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

    asyncio.run(backend.write_many({"max_pixel": 64}))

    assert names == ["max_pixel"]


def test_dict_registers_skip_defaults_left_unset() -> None:
    """Keep a register's initial value where the defaults hold `None` for it."""
    values = DictRegisters(fake_specs(), {"max_pixel": None}).values

    assert values["max_pixel"] == 0


def test_a_stuck_write_does_not_hold_up_the_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the event loop close while a write waits on the board."""
    manager = connected_manager()
    release = threading.Event()
    monkeypatch.setattr(manager, "set_registers_dict", lambda registers: release.wait())
    backend = ManagerRegisters(manager)

    async def main() -> None:
        write = asyncio.ensure_future(backend.write_many({"max_pixel": 1}))
        await asyncio.sleep(0.05)
        write.cancel()

    started = time.monotonic()
    try:
        asyncio.run(main())
        assert time.monotonic() - started < 1
    finally:
        release.set()


def quick_config() -> AcquisitionConfig:
    """Return the configuration of a run over a 4 by 4 grid of one frame, which takes 1.3 ms."""
    settings = settings_of(window_config())
    settings.update({"grid.pixels": 4, "grid.lines": 4, "grid.frames": 1})
    return run_config(settings, RunSettings(1, "", False), window_config().detector)


def test_a_simulated_run_writes_the_run_registers_then_the_start_pulse() -> None:
    """Write each run register group in order, then the start pulse, through write_many."""
    backend = StubBackend({})
    config = quick_config()

    async def run() -> None:
        await backend.prepare_run(config)
        await backend.start()

    asyncio.run(run())

    expected = [
        *run_registers(config),
        {"stop_command": False, "start_command": True},
        {"start_command": False},
    ]
    assert [group.keys() for group in backend.written] == [group.keys() for group in expected]
    for written, group in zip(backend.written, expected, strict=True):
        for name, value in group.items():
            np.testing.assert_array_equal(written[name], value, err_msg=name)


def test_a_simulated_run_is_done_once_its_duration_has_passed() -> None:
    """Report a simulated run as not done before start and done after its duration."""
    backend = DictRegisters(fake_specs(), {})

    async def run() -> tuple[RunStatus, RunStatus]:
        await backend.prepare_run(quick_config())
        before = await backend.run_status()
        await backend.start()
        await asyncio.sleep(0.05)
        return before, await backend.run_status()

    before, after = asyncio.run(run())

    assert before.done is False
    assert after == RunStatus(done=True, almost_done=True, fifos_complete=True, workers_alive=True)


def test_manager_registers_start_a_run_in_the_window_order() -> None:
    """Reset the board, prepare, clear the done events, start the pipeline, then pulse start."""
    manager = MagicMock(spec=McsManager)
    backend = ManagerRegisters(manager)
    config = quick_config()

    async def run() -> None:
        await backend.reset()
        await backend.prepare_run(config)
        await backend.run_pipeline()
        await backend.start()

    asyncio.run(run())

    assert [name for name, _, _ in manager.mock_calls] == [
        "quick_reset_fpga",
        "prepare_run",
        "acquisition_done_reset",
        "acquisition_almost_done_reset",
        "run",
        "start",
    ]
    assert manager.prepare_run.call_args == call(config)


def test_manager_registers_finish_stops_the_pipeline_when_the_reset_fails() -> None:
    """Still stop the pipeline and the acquisition when the reset raises, then raise its error."""
    manager = MagicMock(spec=McsManager)
    manager.quick_reset_fpga.side_effect = TimeoutError("not idle")
    backend = ManagerRegisters(manager)

    with pytest.raises(TimeoutError, match="not idle"):
        asyncio.run(backend.finish())

    manager.stop_preview.assert_called_once_with()
    manager.stop_acquisition.assert_called_once_with()


def test_manager_registers_report_a_dead_worker() -> None:
    """Report the workers as not alive when a started data process has stopped."""
    manager = MagicMock(spec=McsManager)
    manager.activated_fifos_list = []
    manager.process_supervisor = MagicMock()
    manager.process_supervisor.is_alive.side_effect = lambda name: name != "preprocess"
    backend = ManagerRegisters(manager)

    status = asyncio.run(backend.run_status())

    assert status.workers_alive is False


def test_manager_registers_ignore_a_worker_never_started() -> None:
    """Report the workers as alive when the run registered none, as with no detector."""
    manager = MagicMock(spec=McsManager)
    manager.activated_fifos_list = []
    manager.process_supervisor = MagicMock()
    manager.process_supervisor.get.return_value = None
    manager.process_supervisor.is_alive.return_value = False
    backend = ManagerRegisters(manager)

    status = asyncio.run(backend.run_status())

    assert status.workers_alive is True
    assert status.fifos_complete is True
