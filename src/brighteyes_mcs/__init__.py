"""BrightEyes-MCS microscope control application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("brighteyes-mcs")
except PackageNotFoundError:
    # a source tree on sys.path or a frozen build carries no installed metadata
    __version__ = "0+unknown"

__all__ = ["__version__"]
