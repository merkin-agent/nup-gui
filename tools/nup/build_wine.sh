#!/usr/bin/env bash
set -euo pipefail

# Cross-build Windows binaries from Linux by running Windows Python and
# PyInstaller under Wine. Requires curl, unzip, Python 3, Wine, and Go.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build_root="${NUP_WIN_BUILD_DIR:-${TMPDIR:-/tmp}/nup-windows-build}"
python_version="3.12.10"
python_dir="$build_root/python"
wheel_dir="$build_root/wheels"
dist_dir="$repo_root/dist"
work_dir="$build_root/pyinstaller-build"
launcher_dir="$repo_root/tools/nup/launcher"
staged_cli="$launcher_dir/nup.exe"
wine_bin="$(command -v wine || true)"
if [[ -z "$wine_bin" ]]; then
  wine_bin="/usr/lib/wine/wine64"
fi
if [[ ! -x "$wine_bin" ]]; then
  echo "Wine not found. Install wine and wine32, then rerun this script." >&2
  exit 1
fi

mkdir -p "$build_root" "$wheel_dir" "$dist_dir"
python3 - "$python_dir" "$wheel_dir" "$work_dir" <<'PY'
import shutil
import sys
from pathlib import Path

for item in map(Path, sys.argv[1:]):
    if item.exists():
        shutil.rmtree(item)
PY
mkdir -p "$python_dir" "$wheel_dir"

curl -fsSL --retry 3 \
  "https://www.python.org/ftp/python/${python_version}/python-${python_version}-embed-amd64.zip" \
  -o "$build_root/python-embed.zip"
python3 -m pip download --only-binary=:all: \
  --platform win_amd64 --python-version 312 --implementation cp --abi cp312 \
  --dest "$wheel_dir" pyinstaller zstandard pefile pywin32-ctypes
unzip -oq "$build_root/python-embed.zip" -d "$python_dir"
python3 - "$wheel_dir" "$python_dir" <<'PY'
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

wheels, runtime = map(Path, sys.argv[1:])
site = runtime / "Lib" / "site-packages"
site.mkdir(parents=True, exist_ok=True)
for wheel in wheels.glob("*.whl"):
    with ZipFile(wheel) as archive:
        archive.extractall(site)
pth = next(runtime.glob("python*._pth"))
pth.write_text("python312.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii")
PY

winpath() {
  local converted="${1//\//\\}"
  printf 'Z:%s' "$converted"
}

export WINEARCH=win64
export WINEPREFIX="${WINEPREFIX:-$HOME/.cache/nup-wine}"
export WINEDEBUG="${WINEDEBUG:--all}"
python_win="$(winpath "$python_dir/python.exe")"
root_win="$(winpath "$repo_root")"
dist_win="$(winpath "$dist_dir")"
work_win="$(winpath "$work_dir")"
mkdir -p "$work_dir"
rm -f "$dist_dir/nup.exe" "$dist_dir/nup-gui.exe"

"$wine_bin" "$python_win" -m PyInstaller \
  --noconfirm --clean --onefile --name nup --console \
  --paths "$root_win\\tools\\nup" --collect-all zstandard \
  --distpath "$dist_win" --workpath "$work_win" --specpath "$work_win" \
  "$root_win\\tools\\nup\\windows_entry.py"

cp "$dist_dir/nup.exe" "$staged_cli"
cleanup() { rm -f "$staged_cli"; }
trap cleanup EXIT
GOOS=windows GOARCH=amd64 go build -ldflags='-H windowsgui' \
  -o "$dist_dir/nup-gui.exe" "$launcher_dir/main_windows.go"

file "$dist_dir/nup.exe" "$dist_dir/nup-gui.exe"
