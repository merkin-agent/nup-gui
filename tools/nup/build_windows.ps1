$ErrorActionPreference = 'Stop'

# Build the self-contained Windows CLI and GUI executables.
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$projectDir = Join-Path $repoRoot 'tools/nup'
$buildDir = Join-Path $projectDir 'build-win'
$distDir = Join-Path $repoRoot 'dist'
$upxVersion = '5.2.1'
$upxDir = Join-Path $env:TEMP "nup-upx-$upxVersion"
$upxZip = Join-Path $env:TEMP "upx-$upxVersion-win64.zip"

python -m pip install --upgrade pip
python -m pip install $projectDir pyinstaller

Invoke-WebRequest `
  -Uri "https://github.com/upx/upx/releases/download/v$upxVersion/upx-$upxVersion-win64.zip" `
  -OutFile $upxZip
$upxHash = (Get-FileHash $upxZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($upxHash -ne 'eabc6792a347d45e945be7748423e7868fd01b0d2bcaa2f4b1031fd71ff69bda') {
  throw 'UPX archive checksum did not match.'
}
Expand-Archive -Path $upxZip -DestinationPath $upxDir -Force
$upxDir = Join-Path $upxDir "upx-$upxVersion-win64"
$upxExe = Join-Path $upxDir 'upx.exe'

if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $distDir | Out-Null
foreach ($name in @('nup.exe', 'nup-gui.exe')) {
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
  & $upxExe --best (Join-Path $distDir 'nup-gui.exe')
  if ($LASTEXITCODE -ne 0) { throw 'UPX failed to compress nup-gui.exe.' }
} finally {
  if (Test-Path $stagedCli) { Remove-Item $stagedCli -Force }
}

Write-Host "Built $distDir/nup.exe and $distDir/nup-gui.exe"
