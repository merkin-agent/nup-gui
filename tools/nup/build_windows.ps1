$ErrorActionPreference = 'Stop'

# Build the self-contained Windows CLI and GUI executables.
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectDir = Join-Path $repoRoot 'tools/nup'
$buildDir = Join-Path $projectDir 'build-win'
$distDir = Join-Path $repoRoot 'dist'

python -m pip install --upgrade pip
python -m pip install $projectDir pyinstaller

if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
foreach ($name in @('nup.exe', 'nup-gui.exe')) {
  $oldExe = Join-Path $distDir $name
  if (Test-Path $oldExe) { Remove-Item $oldExe -Force }
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name nup `
  --console `
  --paths (Join-Path $projectDir '.') `
  --collect-all zstandard `
  --distpath $distDir `
  --workpath $buildDir `
  --specpath $buildDir `
  (Join-Path $projectDir 'windows_entry.py')

& go version
if ($LASTEXITCODE -ne 0) { throw 'Go is required to build nup-gui.exe.' }

$launcherDir = Join-Path $projectDir 'launcher'
$stagedCli = Join-Path $launcherDir 'nup.exe'
Copy-Item (Join-Path $distDir 'nup.exe') $stagedCli -Force
try {
  $env:GOOS = 'windows'
  $env:GOARCH = 'amd64'
  & go build -ldflags '-H windowsgui' -o (Join-Path $distDir 'nup-gui.exe') `
    (Join-Path $launcherDir 'main_windows.go')
  if ($LASTEXITCODE -ne 0) { throw 'Go failed to build nup-gui.exe.' }
} finally {
  if (Test-Path $stagedCli) { Remove-Item $stagedCli -Force }
}

Write-Host "Built $distDir/nup.exe and $distDir/nup-gui.exe"
