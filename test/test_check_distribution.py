import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.check_distribution import REQUIRED_WHEEL_FILES, check_distribution

METADATA = "License-Expression: GPL-3.0-or-later\nRequires-Dist: psutil\n"


def write_distributions(directory: Path, extra: str | None = None) -> None:
    """Write a wheel and an sdist holding the required resources plus `extra`."""
    package_files = sorted(REQUIRED_WHEEL_FILES | ({extra} if extra else set()))
    with zipfile.ZipFile(directory / "brighteyes_mcs-1.0.0-py3-none-any.whl", "w") as wheel:
        for name in package_files:
            wheel.writestr(name, "")
        wheel.writestr("brighteyes_mcs-1.0.0.dist-info/METADATA", METADATA)
    with tarfile.open(directory / "brighteyes_mcs-1.0.0.tar.gz", "w:gz") as sdist:
        for name in package_files:
            info = tarfile.TarInfo(f"brighteyes_mcs-1.0.0/src/{name}")
            sdist.addfile(info, io.BytesIO(b""))


def test_shipped_resources_pass(tmp_path: Path) -> None:
    """Accept distributions that hold only the shipped configuration files."""
    write_distributions(tmp_path)

    check_distribution(tmp_path)


@pytest.mark.parametrize(
    "extra",
    ["brighteyes_mcs/cfg/mylab.cfg", "brighteyes_mcs/bitfiles/firmware.lvbitx"],
    ids=["lab-configuration", "firmware"],
)
def test_local_files_are_refused(tmp_path: Path, extra: str) -> None:
    """Refuse a local configuration file or firmware left in the package directory."""
    write_distributions(tmp_path, extra)

    with pytest.raises(RuntimeError, match="Local or proprietary files"):
        check_distribution(tmp_path)
