# Repository instructions

## Keep this guide current

When you change the Codespace, devcontainer, Windows build, Python version,
dependencies, artifact paths, or validation workflow, update this file in the
same change. Future agents should check these instructions before building and
revise them whenever they learn a recovery step that is not documented here.

## Project map

- `tools/nup/nup/` is the Python NUP container implementation.
- `tools/nup/windows_gui.py` is the Tkinter desktop GUI entry point.
- `tools/nup/build_windows.ps1` is the native Windows build script.
- `tools/nup/build_wine.sh` builds the Windows executable from Linux using
  Windows Python and PyInstaller under Wine.
- `.devcontainer/` defines the Codespace Python and Wine build environment.
- `dist/nup-gui.exe` and `dist/nup-gui-windows-x64.zip` are generated build
  outputs and are ignored by Git. Rebuild them when needed; do not assume they
  survive a Codespace deletion.

Python packaging files live in `tools/nup/`. Run the test suite from the repo
root with:

```sh
PYTHONPATH=tools/nup python -m unittest discover -s tools/nup/tests -v
```

## Cold-start or recover a damaged Codespace

1. Reopen the repository Codespace and check `git status`, the current branch,
   and recent commits before changing files. A deleted or corrupted workspace
   can contain uncommitted work that Git cannot recover; inspect available
   branches and remotes before assuming a file was never present.
2. If `.devcontainer/` is missing or damaged, recover any committed version
   first, for example with `git show <commit>:.devcontainer/Dockerfile` and
   `git show <commit>:.devcontainer/devcontainer.json`. The repository's
   devcontainer installs Python 3.12, multiarch Wine (32-bit and 64-bit), and
   Xvfb for headless Windows builds. After restoring it, use **Codespaces:
   Rebuild Container** so the Dockerfile and `postCreateCommand` run.
3. If the devcontainer cannot be rebuilt, bootstrap the host environment on
   Ubuntu/Debian with:

   ```sh
   sudo dpkg --add-architecture i386
   sudo apt-get update
   sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
     ca-certificates curl git unzip file wine wine64 wine32 xvfb xauth
   python3 -m pip install --user -e ./tools/nup
   ```

   Wine needs a 64-bit prefix for the Windows Python installer. If the default
   `~/.cache/nup-wine` was created as 32-bit, leave it intact and select a new
   prefix for the build, such as `~/.cache/nup-wine64`.
4. Build from the repository root:

   ```sh
   WINEPREFIX="$HOME/.cache/nup-wine64" tools/nup/build_wine.sh
   ```

   The script selects `/usr/lib/wine/wine64` when available and starts itself
   under `xvfb-run` when no display is set. Wine 9 does not implement
   `CopyFile2`; during pip installation only, the script temporarily disables
   Python's `shutil` fast-copy call and restores the original standard library
   before PyInstaller runs. If the Windows Python installation in
   `/tmp/nup-windows-build/python` is already complete, set
   `NUP_WIN_REUSE_PYTHON=1` to reuse it rather than reinstalling Python.

The build uses Windows Python 3.12.10 and follows the 0.1.9 release's
PyInstaller options: one-file, windowed, no UPX, collect `zstandard`, bundle
the GUI icon, and exclude unused SSL modules. PyInstaller and Python packaging
dependencies are intentionally installed the same way as in
`build_windows.ps1` (not pinned to a different release profile).

## Build outputs and checks

The Wine build writes:

- `dist/nup-gui.exe` — Windows x64 GUI executable.
- `dist/nup-gui-windows-x64.zip` — ZIP containing only `nup-gui.exe`.

Check the output with `file dist/nup-gui.exe` and
`unzip -l dist/nup-gui-windows-x64.zip`. A headless GUI startup check can be
run with Wine under Xvfb; allow it to remain open briefly, then terminate it.
`tools/nup/smoke_gui.py` uses Windows-only `ctypes` APIs and is intended for the
Windows CI runner, not the Linux Wine host.

The NUP application icon is stored in metadata TLV `0x0003`. Packing accepts
explicit `-i/--icon` or detects common artwork and Switch `icon_*.dat` files;
GUI packaging also accepts a title and display version. Keep metadata injection
and unpack extraction behavior aligned across the CLI and GUI. Legacy packages
without artwork must remain extractable and should report a missing-artwork
warning rather than losing their package tree.
