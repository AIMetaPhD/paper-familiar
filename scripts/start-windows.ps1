# PaperFamiliar native launcher for Windows 11 (PowerShell 5.1+).
# Creates a local virtual environment, installs the pinned dependencies, and
# starts the workbench at http://127.0.0.1:8420. End users do not need admin
# rights, Docker, WSL or Node: the web build is shipped.
param(
    [int]$Port = 8420,
    [switch]$NoBrowser,
    [switch]$Reinstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$script:Python = $null

function Fail([string]$Message, [int]$Code = 2) {
    Write-Host ""
    Write-Host "PaperFamiliar could not start:" -ForegroundColor Red
    Write-Host "  $Message" -ForegroundColor Red
    Write-Host ""
    Write-Host "Diagnostics:" -ForegroundColor Yellow
    Write-Host "  root:    $Root"
    Write-Host "  python:  $script:Python"
    Write-Host "  port:    $Port"
    exit $Code
}

$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $candidates += ,@("py", "-3.13")
    $candidates += ,@("py", "-3.12")
    $candidates += ,@("py", "-3.11")
}
$candidates += ,@("python")

$PythonCmd = @()
foreach ($candidate in $candidates) {
    $cmd = @($candidate)
    try {
        $exe = [string]$cmd[0]
        $extra = @()
        if ($cmd.Count -gt 1) { $extra = $cmd[1..($cmd.Count - 1)] }
        $version = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        $parts = $version.Trim().Split(".")
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        if ($major -eq 3 -and $minor -ge 11 -and $minor -le 13) {
            $script:Python = $exe
            $PythonCmd = @($exe) + $extra
            break
        }
    } catch { continue }
}

if (-not $script:Python) {
    Fail "Python 3.11-3.13 was not found. Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'." 3
}

Write-Host "PaperFamiliar" -ForegroundColor Green
Write-Host "  python: $($PythonCmd -join ' ')"
Write-Host "  root:   $Root"

$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if ($Reinstall -and (Test-Path $Venv)) {
    Remove-Item -Recurse -Force $Venv
}
if (-not (Test-Path $VenvPython)) {
    Write-Host "  creating .venv ..."
    $exe = [string]$PythonCmd[0]
    $extra = @()
    if ($PythonCmd.Count -gt 1) { $extra = $PythonCmd[1..($PythonCmd.Count - 1)] }
    & $exe @extra -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv failed." 4 }
}

$Dist = Join-Path $Root "src\paperfamiliar\web\dist\index.html"
if (-not (Test-Path $Dist)) {
    Fail "The web build is missing (src/paperfamiliar/web/dist). Run 'npm --prefix web install; npm --prefix web run build' once in a development box." 5
}

& $VenvPython -c "import fastapi, uvicorn, pylatexenc" 2>$null
if ($LASTEXITCODE -ne 0 -or $Reinstall) {
    $Wheelhouse = Join-Path $Root "wheelhouse"
    if (Test-Path $Wheelhouse) {
        Write-Host "  installing from the offline wheelhouse ..."
        & $VenvPython -m pip install --disable-pip-version-check --no-index --find-links $Wheelhouse -e .
    } else {
        Write-Host "  installing from the network (first run only) ..."
        & $VenvPython -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
        & $VenvPython -m pip install --disable-pip-version-check -e .
    }
    if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed. Check the network or build a wheelhouse." 6 }
}

$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Fail "Port $Port is already in use by process $($busy[0].OwningProcess). Close it or pass -Port 8421." 7
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$argsList = @("-m", "paperfamiliar", "serve", "--port", "$Port")
if ($NoBrowser) { $argsList += "--no-browser" }

Write-Host "  starting http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  press Ctrl+C to stop" -ForegroundColor DarkGray
& $VenvPython @argsList
exit $LASTEXITCODE
