# Contributing to BrightEyes-MCS

Report bugs with reproduction steps, operating system, Python version, detector,
and firmware details. For a substantial feature, discuss the intended behavior
with the maintainers before changing acquisition code.

## Development environment

Use a source checkout and Python 3.11 or later (64-bit) on Windows. The
development environment is managed with [uv](https://docs.astral.sh/uv/), which
installs the versions pinned in `uv.lock`. From the repository root:

```powershell
uv sync
.\.venv\Scripts\Activate.ps1
```

`uv sync` creates `.venv` with the project in editable mode and the `dev`
dependency group. Without activating it, prefix a command with `uv run`.
In Command Prompt use `.venv\Scripts\activate.bat`. Package metadata and
runtime dependencies are defined in [pyproject.toml](pyproject.toml); add or
change a dependency with `uv add` so the lock file follows.
NI drivers and matching firmware are needed for physical acquisition, not for
the mocked unit tests. Do not commit local microscope profiles, data, or firmware.

## Validation

Run from the repository root:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m unittest test.test_channel_delay_skew_plugin -v
python -m pytest -q -m qt_isolated test/test_console_widget.py
python scripts/check_docs.py
python scripts/check_lint.py
python -m compileall -q src scripts
```

The normal pytest command excludes `qt_isolated` tests. Run the channel-delay
widget and real in-process console suites separately with the commands above:
mixing Qt/Jupyter lifetimes and multiprocessing tests can crash Windows/Python
3.13. The Windows CI template runs these isolated suites on 3.13.
Tests requiring external tools may skip when those tools are unavailable;
inspect the skip summary with `python -m pytest -q -rs`.

The lint checker rejects findings beyond the reviewed legacy baseline in
[scripts/lint_baseline.json](scripts/lint_baseline.json). Extracted statistics and
new validation modules must be clean. Do not use blanket suppressions or unsafe
automatic fixes. After removing legacy findings, regenerate the baseline with
`python scripts/check_lint.py --write-baseline` and review the diff; never use
that command simply to accept new findings. Ruff is pinned for reproducibility.

For distribution changes also run `uv build`, `uvx twine check dist/*`,
and `python scripts/check_distribution.py dist`; use a clean output directory.
See the [release guide](docs/pypi-release.md) before publishing. Publication is disabled.

## Editing the Qt UI

Edit the Designer `.ui` source, then regenerate its Python module. For the main window:

```powershell
pyside6-uic src/brighteyes_mcs/ui/qt/main_window_design.ui -o src/brighteyes_mcs/ui/qt/main_window_design.py
```

Use the compiler from the active environment and review the generated diff.
Never hand-edit generated `*_design.py` modules. Commit the `.ui` and generated
module together. Check dock resizing and representative populated values, not
only the empty form.

## Code and documentation changes

Keep refactors small and preserve configuration, HDF5/RAW, REST, plug-in, and
FPGA contracts. Follow the [architecture boundaries](docs/refactoring-architecture.md).
Put calculations in Qt-independent controllers; keep timers, signals, and widgets
in the UI. Add tests for behavior or failure paths, not implementation details.

The [documentation index](docs/README.md) is the maintained entry point. Update
related guides in the same change, use relative repository links, and distinguish
current behavior from historical examples. The optional external link report is
`python scripts/check_docs.py --external`; it does not make network failures a
merge blocker.

Submit a pull request describing the problem, resulting behavior, and validation.
Instrument behavior remains unverified until a connected-hardware smoke test is
performed. See the [hardware acceptance checklist](docs/refactoring-architecture.md#hardware-acceptance-checklist).
