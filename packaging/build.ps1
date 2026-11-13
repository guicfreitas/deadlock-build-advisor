# Build the Windows .exe (PyInstaller) and the installer (Inno Setup).
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Needs: .venv-build with pyinstaller (python -m venv .venv-build; .venv-build\Scripts\pip install pyinstaller)
#        Inno Setup 6 (winget install JRSoftware.InnoSetup)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path "src\deadlock_advisor\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Deadlock Build Advisor $version"

$py = Join-Path $root ".venv-build\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Falta o ambiente de build: python -m venv .venv-build; .venv-build\Scripts\pip install pyinstaller" }

& $py -m PyInstaller --noconfirm --clean `
    --name DeadlockBuildAdvisor `
    --windowed `
    --icon "$root\packaging\icon.ico" `
    --paths "$root\src" `
    --add-data "$root\src\deadlock_advisor\web;deadlock_advisor\web" `
    --add-data "$root\src\deadlock_advisor\locales;deadlock_advisor\locales" `
    --distpath dist --workpath build\pyinstaller --specpath build `
    "$root\packaging\launcher.py"
if ($LASTEXITCODE) { throw "PyInstaller falhou" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado (winget install JRSoftware.InnoSetup)" }
& $iscc /Qp "/DAppVersion=$version" packaging\installer.iss
if ($LASTEXITCODE) { throw "Inno Setup falhou" }
# checksum next to the installer: the in-app updater refuses a release without one
$setup = "dist\DeadlockBuildAdvisor-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$setup.sha256" -Value "$hash  DeadlockBuildAdvisor-Setup-$version.exe" -Encoding ascii -NoNewline
Get-ChildItem dist\*.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length / 1MB) }
