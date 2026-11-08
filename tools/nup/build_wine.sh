#!/usr/bin/env bash
set -euo pipefail

# Build the Windows GUI from Linux using Windows Python under Wine.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
build_root="${NUP_WIN_BUILD_DIR:-${TMPDIR:-/tmp}/nup-windows-build}"
python_version="3.12.10"
python_dir="$build_root/python"
python_installer="$build_root/python-installer.exe"
dist_dir="$repo_root/dist"
work_dir="$build_root/pyinstaller-build"
wine_bin="$(command -v wine || true)"
if [[ -z "$wine_bin" ]]; then
  wine_bin="/usr/lib/wine/wine64"
fi
if [[ ! -x "$wine_bin" ]]; then
  echo "Wine not found. Install wine and wine32, then rerun this script." >&2
  exit 1
fi

mkdir -p "$build_root" "$dist_dir"
python3 - "$python_dir" "$work_dir" <<'PY'
import shutil
import sys
from pathlib import Path

for item in map(Path, sys.argv[1:]):
    if item.exists():
        shutil.rmtree(item)
PY

curl -fsSL --retry 3 \
  "https://www.python.org/ftp/python/${python_version}/python-${python_version}-amd64.exe" \
  -o "$python_installer"

winpath() {
  local converted="${1//\//\\}"
  printf 'Z:%s' "$converted"
}

export WINEARCH=win64
export WINEPREFIX="${WINEPREFIX:-$HOME/.cache/nup-wine}"
export WINEDEBUG="${WINEDEBUG:--all}"
python_win="$(winpath "$python_dir/python.exe")"
python_dir_win="$(winpath "$python_dir")"
installer_win="$(winpath "$python_installer")"
root_win="$(winpath "$repo_root")"
dist_win="$(winpath "$dist_dir")"
work_win="$(winpath "$work_dir")"
icon_win="$(winpath "$repo_root/tools/nup/launcher/assets/NUP_GUI_Packager.ico")"
gui_entry_win="$root_win\\tools\\nup\\windows_gui.py"

"$wine_bin" "$installer_win" /quiet \
  "TargetDir=$python_dir_win" \
  InstallAllUsers=0 Include_launcher=0 Include_pip=1 Include_tcltk=1 \
  Include_test=0 PrependPath=0 Shortcuts=0

"$wine_bin" "$python_win" -m pip install --upgrade pip
"$wine_bin" "$python_win" -m pip install "$root_win\\tools\\nup" pyinstaller

mkdir -p "$work_dir"
rm -f "$dist_dir/nup-gui.exe" "$dist_dir/nup-gui-windows-x64.zip"

"$wine_bin" "$python_win" -m PyInstaller \
  --noconfirm --clean --onefile --windowed --noupx \
  --name nup-gui --paths "$root_win\\tools\\nup" --collect-all zstandard \
  --exclude-module _hashlib --exclude-module _ssl --exclude-module ssl \
  --icon "$icon_win" --add-data "${icon_win};assets" \
  --distpath "$dist_win" --workpath "$work_win\\gui" --specpath "$work_win\\gui" \
  "$gui_entry_win"

python3 - "$dist_dir" <<'PY'
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

dist = Path(sys.argv[1])
with ZipFile(dist / "nup-gui-windows-x64.zip", "w", ZIP_DEFLATED, compresslevel=9) as archive:
    archive.write(dist / "nup-gui.exe", "nup-gui.exe")
PY

file "$dist_dir/nup-gui.exe"
ls -lh "$dist_dir/nup-gui-windows-x64.zip"
