"""Pin how the mcs service starts, serves its registers over PVAccess and stops."""

import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from p4p.client.thread import Context, RemoteError

from brighteyes_mcs.acquisition.manager import McsManager
from brighteyes_mcs.services.mcs import STOP_DEADLINE, stop_board
from test.fake_bitfile import SETTINGS_REGISTERS, write_fake_bitfile

READY = "mcs ready"


def start_service(*arguments: str) -> tuple[subprocess.Popen[str], str]:
    """Start the service with `arguments` as a session would; return it and its prefix."""
    prefix = f"BETEST{os.getpid()}"
    environment = {
        **os.environ,
        "REDSUN_SERVICE_NAME": "mcs",
        "REDSUN_SERVICE_PREFIX": prefix,
        "REDSUN_SERVICE_READY": READY,
        "EPICS_PVAS_INTF_ADDR_LIST": "127.0.0.1",
        "EPICS_PVAS_SERVER_PORT": "0",
        "PYTHONUTF8": "1",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "brighteyes_mcs.services.mcs", *arguments],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    return process, prefix


def wait_for_ready(process: subprocess.Popen[str]) -> None:
    """Read the service's output on a thread until its ready line, failing after 30 s."""
    assert process.stdout is not None
    stdout = process.stdout
    seen = threading.Event()

    def read() -> None:
        for line in stdout:
            if line.strip() == READY:
                seen.set()
                return

    threading.Thread(target=read, daemon=True).start()
    if not seen.wait(30):
        process.kill()
        pytest.fail("the service did not print its ready line within 30 s")


def wait_for(predicate: Callable[[], bool], timeout: float) -> bool:
    """Return whether `predicate()` holds within `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_the_service_serves_registers_and_stops_cleanly(tmp_path: Path) -> None:
    """Serve the registers, check written values, and stop with code 0 when asked."""
    process, prefix = start_service("--simulate", "--bitfile", str(write_fake_bitfile(tmp_path)))
    wait_for_ready(process)
    client = Context(
        "pva", conf={"EPICS_PVA_ADDR_LIST": "127.0.0.1", "EPICS_PVA_AUTO_ADDR_LIST": "NO"}
    )
    try:
        assert client.get(f"{prefix}:Simulated")
        client.put(f"{prefix}:Registers:MaxPixel", 9)
        assert wait_for(lambda: client.get(f"{prefix}:Registers:MaxPixel_RBV") == 9, 2)
        # FastCS checks the value before the step that answers a refused put,
        # so the client sees its own timeout rather than an error.
        # TODO: ask FastCS for a patch answering such a put with its error,
        # then expect RemoteError here.
        with pytest.raises(TimeoutError):
            client.put(f"{prefix}:Registers:AnalogOutput7SourceSelector", 300, timeout=1)
        assert client.get(f"{prefix}:Registers:AnalogOutput7SourceSelector_RBV") == 0
        with pytest.raises(RemoteError):
            client.put(f"{prefix}:Registers:CurrentXIndex", 1)
    finally:
        client.close()
        assert process.stdin is not None
        process.stdin.close()

    assert process.wait(timeout=STOP_DEADLINE) == 0


def test_a_physical_setting_is_served_over_pva(tmp_path: Path) -> None:
    """Put a range over PVA in simulation and read its value back."""
    bitfile = write_fake_bitfile(tmp_path, SETTINGS_REGISTERS)
    process, prefix = start_service("--simulate", "--bitfile", str(bitfile))
    wait_for_ready(process)
    client = Context(
        "pva", conf={"EPICS_PVA_ADDR_LIST": "127.0.0.1", "EPICS_PVA_AUTO_ADDR_LIST": "NO"}
    )
    try:
        client.put(f"{prefix}:Scanner:X:RangeUm", 20.0)
        assert wait_for(lambda: abs(client.get(f"{prefix}:Scanner:X:RangeUm_RBV") - 20.0) < 1e-3, 2)
    finally:
        client.close()
        assert process.stdin is not None
        process.stdin.close()

    assert process.wait(timeout=STOP_DEADLINE) == 0


def test_a_zero_calibration_stops_the_service(tmp_path: Path) -> None:
    """Exit with code 1, without the ready line, when a calibration argument is zero."""
    bitfile = write_fake_bitfile(tmp_path, SETTINGS_REGISTERS)
    process, _ = start_service(
        "--simulate", "--bitfile", str(bitfile), "--calibration", "1", "0", "1"
    )

    output, _ = process.communicate(timeout=30)

    assert process.returncode == 1
    assert READY not in output.splitlines()


def test_a_missing_bitfile_stops_the_service_before_ready(tmp_path: Path) -> None:
    """Exit with a non-zero code, without the ready line, when the bitfile is missing."""
    process, _ = start_service("--simulate", "--bitfile", str(tmp_path / "absent.lvbitx"))

    output, _ = process.communicate(timeout=15)

    assert process.returncode != 0
    assert READY not in output.splitlines()


def manager() -> McsManager:
    """Return a manager whose process manager is a mock."""
    with patch("brighteyes_mcs.acquisition.manager.mp.Manager"):
        return McsManager()


def test_stop_board_gives_up_at_its_deadline(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give up on a stop that blocks, logging an error, and finish one that returns."""
    release = threading.Event()
    stuck = manager()
    monkeypatch.setattr(stuck, "stop_fpga", release.wait)
    started = time.monotonic()

    with caplog.at_level(logging.ERROR, logger="brighteyes_mcs"):
        assert stop_board(stuck, 0.2) is False
    release.set()

    assert time.monotonic() - started < 1
    assert caplog.records
    stopping = manager()
    monkeypatch.setattr(stopping, "stop_fpga", lambda: None)
    assert stop_board(stopping, 0.2) is True
    stopping.mp_manager.shutdown.assert_called_once_with()


def test_stop_board_has_nothing_to_stop_in_simulation() -> None:
    """Report a clean stop when the service ran without a manager."""
    assert stop_board(None, 0.2) is True
