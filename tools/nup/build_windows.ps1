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
foreach ($name in @('nup.exe', 'nup-gui.exe', 'nup-gui-windows-x64.zip')) {
  $oldExe = Join-Path $distDir $name
  if (Test-Path $oldExe) { Remove-Item $oldExe -Force }
}

# NUP only uses SHA-256; Python's built-in SHA implementation replaces OpenSSL.
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name nup `
  --console `
  --paths (Join-Path $projectDir '.') `
  --collect-all zstandard `
  --exclude-module _hashlib `
  --exclude-module _ssl `
  --exclude-module ssl `
  --distpath $distDir `
  --workpath $buildDir `
  --specpath $buildDir `
  (Join-Path $projectDir 'windows_entry.py')
& (Join-Path $distDir 'nup.exe') --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The bundled nup.exe failed its startup check.' }

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

Compress-Archive -LiteralPath (Join-Path $distDir 'nup-gui.exe') `
  -DestinationPath (Join-Path $distDir 'nup-gui-windows-x64.zip') `
  -CompressionLevel Optimal

Write-Host "Built $distDir/nup-gui-windows-x64.zip"
