# Publishing BrightEyes-MCS to PyPI

> Publishing is currently disabled. The template is
> [release.yml.disable](../.github/workflows/release.yml.disable); pushing a tag
> does not publish a package. The steps below describe a future maintainer release
> after explicitly enabling the workflow and configuring the publisher.
> Public release availability has not been verified for this guide.

The repository uses a root package layout: the import package is
`brighteyes_mcs/`, built with the `uv_build` backend, which packages that
directory only. A move to `src/brighteyes_mcs/` is not required for
publication.

The Python package contains application code, default configuration, Qt forms,
the About page, and application icons. FPGA `.lvbitx` firmware, user or lab
configuration, notebooks, logs, installers, and development data are not part
of the distributions.

BrightEyes-MCS intentionally declares no console or GUI script entry point.
This prevents pip from generating `brighteyes-mcs.exe` on Windows. Users launch
the installed package with `python -m brighteyes_mcs`; the optional application
Desktop shortcut targets the selected environment's `pythonw.exe` with those
module arguments. A second optional shortcut opens `cmd.exe` and activates the
same Python environment; it does not install an executable or entry point.

## One-time setup

1. Confirm that Istituto Italiano di Tecnologia and the contributors authorize
   distribution under `GPL-3.0-or-later`.
2. Create a protected GitHub environment named `pypi`. Requiring a maintainer's
   approval before deployment is recommended.
3. In the PyPI account that will own the project, create a pending Trusted
   Publisher with:

   - PyPI project: `brighteyes-mcs`
   - GitHub owner: `VicidominiLab`
   - Repository: `BrightEyes-MCS`
   - Workflow: `release.yml`
   - Environment: `pypi`

The workflow template uses OpenID Connect and does not require a stored PyPI API token.

## Preparing a release

Set the version with `uv version VERSION` (it writes `pyproject.toml`, and
`brighteyes_mcs.__version__` reads it from the installed package), add release
notes, and run from a clean checkout:

```powershell
uv sync --locked
uv run pytest -q
uv run python -m unittest test.test_channel_delay_skew_plugin -v
uv build
uvx twine check dist/*
uv run python scripts/check_distribution.py dist
uv run python -m brighteyes_mcs --no-first-run
```

Replace `VERSION` in the examples with the version being released.

For a TestPyPI rehearsal, upload the same artifacts using a TestPyPI account
and install them while allowing production PyPI to supply dependencies:

```powershell
uv publish --publish-url https://test.pypi.org/legacy/ dist/*
python -m pip install --index-url https://test.pypi.org/simple/ `
  --extra-index-url https://pypi.org/simple/ brighteyes-mcs==VERSION
```

TestPyPI and PyPI do not permit replacing a file with the same project name and
version. Increment the version before retrying an upload whose files were
already accepted.

## Publishing

After configuring the publisher and explicitly enabling the release workflow,
commit and merge the release changes, then create and push a version tag that
exactly matches the version in `pyproject.toml`:

```powershell
git tag -a vVERSION -m "BrightEyes-MCS VERSION"
git push origin vVERSION
```

Once enabled, the `Publish Python package` workflow builds from the tag, verifies the version,
checks metadata and archive contents, and publishes through the configured
PyPI Trusted Publisher. Never build a release from a working tree containing
uncommitted changes.
