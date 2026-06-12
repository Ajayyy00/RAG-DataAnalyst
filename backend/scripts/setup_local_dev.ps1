<#
.SYNOPSIS
    Sets up local development environment for Healthcare Copilot on Windows.
    Installs PostgreSQL 16 and Redis 7 natively (no Docker required).

.DESCRIPTION
    This script:
    1. Installs PostgreSQL 16 via winget (if not present)
    2. Installs Redis 7 for Windows via winget (if not present)
    3. Creates the 'healthcopilot' database and 'hc_user' role
    4. Starts both services
    5. Installs Python dependencies into the .venv

.NOTES
    Run this as a regular user (not Administrator).
    PostgreSQL service will be registered as a Windows service.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── Colours ────────────────────────────────────────────────────────────────
function Write-Step  { param($msg) Write-Host "`n>>> $msg" -ForegroundColor Cyan }
function Write-Ok    { param($msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  ⚠ $msg" -ForegroundColor Yellow }
function Write-Err   { param($msg) Write-Host "  ✗ $msg" -ForegroundColor Red }

# ─── Config (match your .env) ────────────────────────────────────────────────
$PG_VERSION  = "16"
$PG_DB       = "healthcopilot"
$PG_USER     = "hc_user"
$PG_PASSWORD = "changeme"
$PG_PORT     = 5432

# ─── 1. Check winget ─────────────────────────────────────────────────────────
Write-Step "Checking winget availability"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Err "winget is not available. Install App Installer from the Microsoft Store first."
    Write-Err "https://apps.microsoft.com/store/detail/app-installer/9NBLGGH4NNS1"
    exit 1
}
Write-Ok "winget found: $(winget --version)"

# ─── 2. Install PostgreSQL ────────────────────────────────────────────────────
Write-Step "Installing PostgreSQL $PG_VERSION"
$pgInstalled = winget list --id "PostgreSQL.PostgreSQL.$PG_VERSION" 2>&1 | Select-String "PostgreSQL"
if ($pgInstalled) {
    Write-Ok "PostgreSQL $PG_VERSION is already installed"
} else {
    Write-Host "  Installing PostgreSQL $PG_VERSION via winget..." -ForegroundColor Yellow
    winget install --id "PostgreSQL.PostgreSQL.$PG_VERSION" --silent --accept-source-agreements --accept-package-agreements
    Write-Ok "PostgreSQL $PG_VERSION installed"
}

# ─── 3. Install Redis ─────────────────────────────────────────────────────────
Write-Step "Installing Redis for Windows"
# Redis official Windows port via Memurai or use WSL2 Redis — try Memurai Community
$redisInstalled = winget list --id "Memurai.Memurai" 2>&1 | Select-String "Memurai"
if ($redisInstalled) {
    Write-Ok "Memurai (Redis-compatible) is already installed"
} else {
    # Fallback: try the Microsoft Archive redis-windows package
    Write-Host "  Trying to install Memurai (Redis for Windows)..." -ForegroundColor Yellow
    try {
        winget install --id "Memurai.Memurai" --silent --accept-source-agreements --accept-package-agreements
        Write-Ok "Memurai installed"
    } catch {
        Write-Warn "Could not install Memurai. Trying redis-windows..."
        try {
            winget install --id "tporadowski.redis" --silent --accept-source-agreements --accept-package-agreements
            Write-Ok "Redis for Windows installed"
        } catch {
            Write-Warn "Could not auto-install Redis."
            Write-Warn "Please install manually: https://github.com/tporadowski/redis/releases"
            Write-Warn "Or use WSL2: wsl --install, then: sudo apt install redis-server && sudo service redis-server start"
        }
    }
}

# ─── 4. Detect psql ──────────────────────────────────────────────────────────
Write-Step "Locating psql"
$psqlPaths = @(
    "C:\Program Files\PostgreSQL\$PG_VERSION\bin\psql.exe",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe",
    "C:\Program Files\PostgreSQL\15\bin\psql.exe"
)
$psql = $null
foreach ($p in $psqlPaths) {
    if (Test-Path $p) { $psql = $p; break }
}
if (-not $psql) {
    # Try PATH
    $psql = (Get-Command psql -ErrorAction SilentlyContinue)?.Source
}
if (-not $psql) {
    Write-Warn "psql not found in common locations. Skipping DB creation."
    Write-Warn "After starting PostgreSQL, run manually:"
    Write-Warn "  psql -U postgres -c `"CREATE USER $PG_USER WITH PASSWORD '$PG_PASSWORD';`""
    Write-Warn "  psql -U postgres -c `"CREATE DATABASE $PG_DB OWNER $PG_USER;`""
} else {
    Write-Ok "psql found: $psql"

    # ─── 5. Start PostgreSQL service ─────────────────────────────────────────
    Write-Step "Starting PostgreSQL service"
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pgService) {
        if ($pgService.Status -ne "Running") {
            Start-Service $pgService.Name
            Start-Sleep -Seconds 3
        }
        Write-Ok "PostgreSQL service is running: $($pgService.Name)"
    } else {
        Write-Warn "No PostgreSQL Windows service found. PostgreSQL may not be installed yet or needs a restart."
    }

    # ─── 6. Create DB + User ─────────────────────────────────────────────────
    Write-Step "Creating database and user"
    $env:PGPASSWORD = "postgres"  # default postgres superuser password during fresh install

    # Check/create user
    $userExists = & $psql -U postgres -p $PG_PORT -tAc "SELECT 1 FROM pg_roles WHERE rolname='$PG_USER';" 2>&1
    if ($userExists -match "1") {
        Write-Ok "User '$PG_USER' already exists"
    } else {
        & $psql -U postgres -p $PG_PORT -c "CREATE USER $PG_USER WITH PASSWORD '$PG_PASSWORD';"
        Write-Ok "User '$PG_USER' created"
    }

    # Check/create database
    $dbExists = & $psql -U postgres -p $PG_PORT -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB';" 2>&1
    if ($dbExists -match "1") {
        Write-Ok "Database '$PG_DB' already exists"
    } else {
        & $psql -U postgres -p $PG_PORT -c "CREATE DATABASE $PG_DB OWNER $PG_USER;"
        & $psql -U postgres -p $PG_PORT -c "GRANT ALL PRIVILEGES ON DATABASE $PG_DB TO $PG_USER;"
        Write-Ok "Database '$PG_DB' created"
    }

    $env:PGPASSWORD = ""
}

# ─── 7. Start Redis ──────────────────────────────────────────────────────────
Write-Step "Starting Redis service"
$redisService = Get-Service -Name "Redis*","Memurai*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($redisService) {
    if ($redisService.Status -ne "Running") {
        Start-Service $redisService.Name
        Start-Sleep -Seconds 2
    }
    Write-Ok "Redis service is running: $($redisService.Name)"
} else {
    Write-Warn "No Redis Windows service found. You may need to start it manually or install it first."
    Write-Warn "For WSL2 Redis: wsl -e bash -c 'sudo service redis-server start'"
}

# ─── 8. Install Python dependencies ─────────────────────────────────────────
Write-Step "Installing Python dependencies into .venv"
$venvPython = Join-Path $PSScriptRoot "..\. venv\Scripts\python.exe"
$venvPython = (Resolve-Path (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe") -ErrorAction SilentlyContinue)?.Path

if ($venvPython -and (Test-Path $venvPython)) {
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot "..\requirements.txt") --quiet
    Write-Ok "Python dependencies installed"
} else {
    Write-Warn ".venv not found. Creating it first..."
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if ($pythonExe) {
        & $pythonExe -m venv (Join-Path $PSScriptRoot "..\.venv")
        $venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
        & $venvPython -m pip install -r (Join-Path $PSScriptRoot "..\requirements.txt") --quiet
        Write-Ok "Python dependencies installed into new .venv"
    } else {
        Write-Warn "Python not found in PATH. Install Python 3.11+ first."
    }
}

# ─── 9. Run Alembic migrations ───────────────────────────────────────────────
Write-Step "Running Alembic database migrations"
$venvAlembic = Join-Path $PSScriptRoot "..\.venv\Scripts\alembic.exe"
if (Test-Path $venvAlembic) {
    Push-Location (Join-Path $PSScriptRoot "..")
    try {
        & $venvAlembic upgrade head
        Write-Ok "Alembic migrations applied"
    } catch {
        Write-Warn "Alembic migration failed: $_"
        Write-Warn "Ensure PostgreSQL is running and .env credentials are correct."
    } finally {
        Pop-Location
    }
} else {
    Write-Warn "alembic not found. Run manually: cd backend && alembic upgrade head"
}

# ─── Summary ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host "  Healthcare Copilot — Local Dev Setup Complete" -ForegroundColor Magenta
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Magenta
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Seed the database:   python scripts/seed_db.py" -ForegroundColor Gray
Write-Host "  2. Start the backend:   .venv\Scripts\uvicorn app.main:app --reload --port 8001" -ForegroundColor Gray
Write-Host "  3. Open API docs:       http://localhost:8001/docs" -ForegroundColor Gray
Write-Host "  4. Start the frontend:  cd ../frontend && npm run dev" -ForegroundColor Gray
Write-Host ""
