import subprocess
import sys

IMPORT_WITHOUT_METADATA = """
import importlib.metadata

def missing(name):
    raise importlib.metadata.PackageNotFoundError(name)

importlib.metadata.version = missing
import brighteyes_mcs
print(brighteyes_mcs.__version__)
"""


def test_import_succeeds_without_installed_metadata() -> None:
    """Import the package and report an unknown version when no metadata is installed."""
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_WITHOUT_METADATA],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0+unknown"
