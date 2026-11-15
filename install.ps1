# One-time setup for Pistachio's Studio on Windows 10/11:   double-click install.bat   (or: powershell -ExecutionPolicy Bypass -File install.ps1 [-3d])
# Makes a private Python environment in .venv, installs what the Studio needs into it, and tells you what to do next.
# It changes nothing outside this folder. It never asks for or stores any key; the Studio's Setup window does that.
param([switch]$3d)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$steps = if ($3d) { 5 } else { 4 }
function Step($n, $text) { Write-Progress -Activity "Installing Pistachio's Studio" -Status "$text ($n of $steps)" -PercentComplete ([int](($n - 1) * 100 / $steps)); Write-Host "== $text ($n of $steps)" }

Step 1 "Looking for Python 3.11 or newer"
$cands = @()
if ($env:PYTHON) { $cands += ,@($env:PYTHON) }
$cands += ,@("py", "-3.13"); $cands += ,@("py", "-3.12"); $cands += ,@("py", "-3.11"); $cands += ,@("python")
$pyExe = $null; $pyPre = @()
foreach ($c in $cands) {
  $pre = @($c | Select-Object -Skip 1)
  try {
    & $c[0] @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $pyExe = $c[0]; $pyPre = $pre; break }
  } catch { }
}
if (-not $pyExe) {
  Write-Host "Python 3.11 or newer was not found (the Kaggle program needs it)."
  Write-Host "Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
  exit 1
}
& $pyExe @pyPre --version

Step 2 "Making the private Python environment (.venv)"
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $pyExe @pyPre -m venv .venv }
$vpy = ".venv\Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Host "pip could not be set up inside .venv; reinstall Python from python.org and run this again."; exit 1 }

Step 3 "Installing the Studio's requirements"
# constraints.txt pins the versions that were tested together
& $vpy -m pip install --quiet -r requirements.txt -c constraints.txt
if ($LASTEXITCODE -ne 0) { Write-Host "Installing the requirements failed; read the messages above."; exit 1 }

if ($3d) {
  Step 4 "Installing the optional 3D depth view (large; this can take several minutes)"
  & $vpy -m pip install --quiet -r requirements-3d.txt
}

Step $steps "Checking the Studio starts"
& $vpy scripts\studio.py --help > $null
Write-Progress -Activity "Installing Pistachio's Studio" -Completed
Write-Host ""
Write-Host "Done. Start the Studio by double-clicking run_studio.bat"
Write-Host "The first time it opens, the Setup window asks for your free Kaggle API token (kaggle.com > Settings > API)."
