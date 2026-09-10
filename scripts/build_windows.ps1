$ErrorActionPreference = "Stop"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 22 or newer is required. Install it from https://nodejs.org/ and reopen PowerShell."
}
if (-not (Get-Command corepack -ErrorAction SilentlyContinue)) {
    throw "Corepack is missing. Reinstall Node.js 22 with Corepack support."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/ and reopen PowerShell."
}

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

corepack prepare pnpm@10.17.1 --activate
Assert-LastExitCode "Corepack pnpm activation"
$env:CI = "true"
corepack pnpm --dir frontend install --frozen-lockfile
Assert-LastExitCode "Frontend dependency installation"
corepack pnpm --dir frontend test -- --run
Assert-LastExitCode "Frontend tests"
corepack pnpm --dir frontend typecheck
Assert-LastExitCode "Frontend typecheck"
corepack pnpm --dir frontend build
Assert-LastExitCode "Frontend build"

& (Join-Path $PSScriptRoot "prepare_ocr.ps1")

$env:UV_CACHE_DIR = Join-Path $env:TEMP "dockmask-uv-cache"
$env:GIGACHAT_RUN_INTEGRATION = "0"
$pytestTemp = Join-Path (Resolve-Path "tmp") ("pytest-build-" + [guid]::NewGuid().ToString("N"))
uv run pytest -q tests --basetemp $pytestTemp
Assert-LastExitCode "Backend tests"
uv run ruff check .
Assert-LastExitCode "Backend lint"
uv lock --check
Assert-LastExitCode "Lockfile validation"
Get-Process -Name DockMask -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

uv run pyinstaller --noconfirm --clean --distpath output/exe --workpath tmp/pyinstaller DockMask.spec
Assert-LastExitCode "PyInstaller build"

$executable = Resolve-Path "output/exe/DockMask.exe"
& $executable --self-test
Assert-LastExitCode "Packaged application self-test"
$distributionFiles = @(Get-ChildItem "output/exe" -Recurse -File)
if ($distributionFiles.Count -ne 1 -or $distributionFiles[0].FullName -ne $executable.Path) {
    throw "Distribution must contain only DockMask.exe"
}
