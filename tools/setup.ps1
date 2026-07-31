<#
    A.N.S Tools bootstrap.

    Gets a machine from "nothing installed" to "the app is running" without the
    user opening a terminal or installing anything by hand. Everything it needs
    lands inside the app folder: a private Python in .python, its packages in
    .venv. Nothing is added to PATH, nothing is installed for all users, and
    nothing needs administrator rights.

    Run by Start.bat. Also useful on its own:

        powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -CheckOnly

    which reports what it found and installs nothing.
#>
[CmdletBinding()]
param(
    # install and launch; without it the script sets up and stops
    [switch]$Launch,
    # report what is present and change nothing
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # the download bar cripples speed

$Root = Split-Path -Parent $PSScriptRoot
$LocalPython = Join-Path $Root '.python'
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$VenvPythonW = Join-Path $Venv 'Scripts\pythonw.exe'
$Requirements = Join-Path $Root 'requirements.txt'
$Stamp = Join-Path $Venv '.requirements-hash'

# The app needs 3.10+. This is what gets installed when the machine has nothing
# usable — a version with a long support window and wheels for everything.
$MinVersion = [Version]'3.10'
$PythonVersion = '3.12.8'
$InstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"

function Write-Step([string]$text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Note([string]$text) { Write-Host "    $text" -ForegroundColor DarkGray }
function Write-Bad([string]$text) { Write-Host "!!  $text" -ForegroundColor Red }

function Get-PythonVersion([string]$exe) {
    <#  The version of a candidate interpreter, or $null if it is unusable.
        Checked by running it: a python.exe on PATH can be a stub, a store
        alias, or 32-bit, and none of those announce themselves.  #>
    if (-not (Test-Path -LiteralPath $exe)) { return $null }
    try {
        $probe = & $exe -c "import sys,struct;print('%d.%d' % sys.version_info[:2], struct.calcsize('P')*8)" 2>$null
    } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $probe) { return $null }
    $parts = "$probe".Trim().Split()
    if ($parts.Count -lt 2 -or $parts[1] -ne '64') { return $null }
    try { return [Version]$parts[0] } catch { return $null }
}

function Find-Python {
    <#  A usable interpreter, preferring the private one this script installed
        so a machine with a broken system Python still starts.  #>
    $candidates = @(Join-Path $LocalPython 'python.exe')
    foreach ($launcher in @('py', 'python')) {
        $command = Get-Command $launcher -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        try {
            $resolved = & $command.Source -3 -c "import sys;print(sys.executable)" 2>$null
        } catch { $resolved = $null }
        if (-not $resolved) {
            try { $resolved = & $command.Source -c "import sys;print(sys.executable)" 2>$null } catch { }
        }
        if ($resolved) { $candidates += "$resolved".Trim() }
    }
    foreach ($candidate in $candidates) {
        $version = Get-PythonVersion $candidate
        if ($version -and $version -ge $MinVersion) {
            return [pscustomobject]@{ Path = $candidate; Version = $version }
        }
    }
    return $null
}

function Install-Python {
    Write-Step "No Python $MinVersion or newer found — installing $PythonVersion privately"
    Write-Note "into $LocalPython (no administrator rights, nothing added to PATH)"
    $installer = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    try {
        Invoke-WebRequest -Uri $InstallerUrl -OutFile $installer -UseBasicParsing
    } catch {
        throw "could not download Python from $InstallerUrl — $($_.Exception.Message)"
    }
    # per-user, private target, no PATH changes, no launcher: this install
    # belongs to the app folder and leaves the machine as it found it
    $arguments = @(
        '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0',
        'Include_test=0', 'Include_doc=0', 'AssociateFiles=0',
        "TargetDir=$LocalPython"
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue
    if ($process.ExitCode -ne 0) {
        throw "the Python installer exited with code $($process.ExitCode)"
    }
    $found = Find-Python
    if (-not $found) { throw "Python installed but could not be run afterwards" }
    return $found
}

function Initialize-Venv([string]$python) {
    if (Test-Path -LiteralPath $VenvPython) { return }
    Write-Step "Creating the app's private package folder"
    & $python -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        throw "could not create a virtual environment in $Venv"
    }
}

function Get-RequirementsHash {
    if (-not (Test-Path -LiteralPath $Requirements)) { return 'none' }
    return (Get-FileHash -LiteralPath $Requirements -Algorithm SHA256).Hash
}

function Install-Dependencies {
    <#  Skipped when requirements.txt has not changed since the last install,
        so a normal launch costs nothing. An update that changes the file
        reinstalls on the next start without anyone being asked.  #>
    $wanted = Get-RequirementsHash
    $have = if (Test-Path -LiteralPath $Stamp) { (Get-Content -LiteralPath $Stamp -Raw).Trim() } else { '' }
    $ready = $false
    if ($have -eq $wanted) {
        & $VenvPython -c "import PySide6" 2>$null
        $ready = ($LASTEXITCODE -eq 0)
    }
    if ($ready) {
        Write-Note "dependencies already installed"
        return
    }
    Write-Step "Installing dependencies (once — this takes a minute)"
    & $VenvPython -m pip install --upgrade pip --disable-pip-version-check --quiet
    & $VenvPython -m pip install --disable-pip-version-check --quiet -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw "pip could not install $Requirements" }
    Set-Content -LiteralPath $Stamp -Value $wanted -Encoding ascii
}

# --------------------------------------------------------------------- run
Write-Host ""
Write-Host "  A.N.S Tools" -ForegroundColor Cyan
Write-Host "  $Root" -ForegroundColor DarkGray
Write-Host ""

$python = Find-Python
if ($python) {
    Write-Step "Python $($python.Version) found"
    Write-Note $python.Path
} elseif ($CheckOnly) {
    Write-Bad "no usable Python — a normal start would install one privately"
} else {
    $python = Install-Python
    Write-Step "Python $($python.Version) installed"
}

if ($CheckOnly) {
    if (Test-Path -LiteralPath $VenvPython) {
        & $VenvPython -c "import PySide6;print('    PySide6', PySide6.__version__)"
    } else {
        Write-Bad "no package folder yet — a normal start would create one"
    }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { Write-Note "git found: $($git.Source)" }
    else { Write-Bad "git not found — in-app updates will not work without it" }
    Write-Host ""
    exit 0
}

Initialize-Venv $python.Path
Install-Dependencies

if (-not $Launch) {
    Write-Step "Ready. Start.bat will open the app."
    exit 0
}

Write-Step "Starting"
# pythonw, so closing this window does not take the app with it and no console
# hangs around behind it
Start-Process -FilePath $VenvPythonW -ArgumentList (Join-Path $Root 'main.py') -WorkingDirectory $Root
