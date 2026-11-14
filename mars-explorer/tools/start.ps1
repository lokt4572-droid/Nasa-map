# MARS EXPLORER - one-click start.
# Run via START-MARS-EXPLORER.bat (double-click). Installs missing dependencies on first run,
# stops old copies of the servers, starts backend + frontend, waits until both answer,
# then opens the app in the default browser.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$AppUrl = "http://127.0.0.1:5173/"
$HealthUrl = "http://127.0.0.1:8000/api/v1/health/"
$Host.UI.RawUI.WindowTitle = "MARS EXPLORER - starter"

function Step($msg) { Write-Host "`n>> $msg" -ForegroundColor DarkYellow }
function Fail($msg) {
    Write-Host "`nERROR: $msg" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
function Test-Url($url) {
    try { (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3).StatusCode -lt 500 } catch { $false }
}

Write-Host "=== MARS EXPLORER ===" -ForegroundColor Red

# 1. Tools available?
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Fail "Python is not installed or not on PATH. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js is not installed or not on PATH. Install the LTS version from https://nodejs.org/" }

# 2. Stop servers left over from a previous start (only this project's).
& (Join-Path $PSScriptRoot "stop.ps1") -Quiet

foreach ($port in 8000, 5173) {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        $name = (Get-Process -Id $busy[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Fail "Port $port is used by another program ($name, PID $($busy[0].OwningProcess)). Close it and try again."
    }
}

# 3. First-run setup.
if (-not (Test-Path $Python)) {
    Step "First run: creating the Python environment (takes a few minutes)..."
    Push-Location $Backend
    python -m venv .venv; if ($LASTEXITCODE) { Fail "Could not create the Python virtual environment." }
    & $Python -m pip install --upgrade pip --quiet
    & $Python -m pip install -r requirements.txt -r requirements-raster.txt --quiet
    if ($LASTEXITCODE) { Fail "Installing Python packages failed (see messages above)." }
    Pop-Location
}
if (-not (Test-Path (Join-Path $Backend ".env"))) { Copy-Item (Join-Path $Backend ".env.example") (Join-Path $Backend ".env") }
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Step "First run: installing frontend packages (takes a minute)..."
    Push-Location $Frontend
    npm install --no-fund --no-audit; if ($LASTEXITCODE) { Fail "npm install failed (see messages above)." }
    Pop-Location
}

Step "Preparing the database..."
Push-Location $Backend
& $Python manage.py migrate --noinput | Out-Null
if ($LASTEXITCODE) { Fail "Database migration failed. Run 'python manage.py migrate' in backend\ to see the error." }
Pop-Location

# 4. Start both servers in their own minimized windows (closing a window stops that server).
Step "Starting the backend (API)..."
Start-Process -FilePath "cmd.exe" -WorkingDirectory $Backend -WindowStyle Minimized `
    -ArgumentList "/k", "title MARS EXPLORER backend - do not close & `"$Python`" manage.py runserver 127.0.0.1:8000"

Step "Starting the frontend (map)..."
Start-Process -FilePath "cmd.exe" -WorkingDirectory $Frontend -WindowStyle Minimized `
    -ArgumentList "/k", "title MARS EXPLORER frontend - do not close & npm run dev"

# 5. Wait until both answer.
Step "Waiting for the servers..."
$deadline = (Get-Date).AddSeconds(90)
$backendUp = $false; $frontendUp = $false
while ((Get-Date) -lt $deadline -and -not ($backendUp -and $frontendUp)) {
    if (-not $backendUp) { $backendUp = Test-Url $HealthUrl }
    if (-not $frontendUp) { $frontendUp = Test-Url $AppUrl }
    Start-Sleep -Milliseconds 700
}
if (-not $frontendUp) { Fail "The frontend did not start. Open the minimized 'MARS EXPLORER frontend' window to see why." }
if (-not $backendUp) { Write-Host "WARNING: the backend did not answer; the map will open but show 'API OFFLINE'. Check the 'MARS EXPLORER backend' window." -ForegroundColor Yellow }

# 6. Open the app.
Step "Opening $AppUrl"
Start-Process $AppUrl
Write-Host "`nMARS EXPLORER is running." -ForegroundColor Green
Write-Host "To stop it, double-click STOP-MARS-EXPLORER.bat (or close the two minimized server windows)."
Start-Sleep -Seconds 4
