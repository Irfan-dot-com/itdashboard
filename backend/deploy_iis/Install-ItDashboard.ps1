<#
.SYNOPSIS
    Install the IT Dashboard cloud side (API + frontend) on Windows / IIS.

.DESCRIPTION
    Sets up the Python virtualenv, installs dependencies, runs Alembic
    migrations, creates the IIS application pools and sites, and applies the
    app-pool settings the API needs (no idle timeout, no periodic recycle).

    Idempotent: safe to re-run to upgrade. It never overwrites an existing
    web.config or an existing database.

    This does NOT install PostgreSQL, a Redis-compatible server,
    HttpPlatformHandler or URL Rewrite. Those are prerequisites — see
    IIS_DEPLOY.md sections 2 and 3.

.PARAMETER RepoRoot
    Path to the checked-out repository (the folder containing backend\ and
    frontend\).

.PARAMETER SiteRoot
    Where the API will be deployed. Default C:\inetpub\itdashboard-api

.PARAMETER WebRoot
    Where the frontend build will be deployed. Default C:\inetpub\itdashboard-web

.PARAMETER PublicUrl
    The public HTTPS URL, e.g. https://dashboard.yourdomain.com
    Baked into the frontend build as VITE_API_BASE_URL.

.PARAMETER DatabaseUrl
    postgresql://user:password@host:5432/dbname

.PARAMETER RedisUrl
    redis://127.0.0.1:6379

.PARAMETER SkipFrontend
    Skip building and deploying the frontend (API only).

.EXAMPLE
    .\Install-ItDashboard.ps1 `
        -RepoRoot C:\MyGIT\it-dashboard `
        -PublicUrl https://dashboard.contoso.com `
        -DatabaseUrl "postgresql://hosp:S3cret@127.0.0.1:5432/hosp_prod" `
        -RedisUrl "redis://127.0.0.1:6379"

.NOTES
    Run in an elevated PowerShell session.
    Written without access to a Windows/IIS host — read it before running, and
    verify afterwards with Test-ItDashboard.ps1.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)] [string] $RepoRoot,
    [string] $SiteRoot = 'C:\inetpub\itdashboard-api',
    [string] $WebRoot  = 'C:\inetpub\itdashboard-web',
    [Parameter(Mandatory = $true)] [string] $PublicUrl,
    [Parameter(Mandatory = $true)] [string] $DatabaseUrl,
    [string] $RedisUrl = 'redis://127.0.0.1:6379',
    [string] $ApiAppPool = 'ItDashboardApi',
    [string] $WebAppPool = 'ItDashboardWeb',
    [string] $ApiSiteName = 'ItDashboardApi',
    [string] $WebSiteName = 'ItDashboardWeb',
    [switch] $SkipFrontend
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Say($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Ok($msg)  { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg){ Write-Host "    WARNING: $msg" -ForegroundColor Yellow }

# --- preconditions ---------------------------------------------------------
Say 'Checking prerequisites'

if (-not ([Security.Principal.WindowsPrincipal] `
          [Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this in an elevated PowerShell session (Run as Administrator).'
}

$backend = Join-Path $RepoRoot 'backend'
if (-not (Test-Path (Join-Path $backend 'app\main.py'))) {
    throw "Cannot find backend\app\main.py under $RepoRoot. Is -RepoRoot correct?"
}
Ok "repo: $RepoRoot"

Import-Module WebAdministration -ErrorAction Stop
Ok 'WebAdministration module loaded'

# Python
$python = (Get-Command python.exe -ErrorAction SilentlyContinue)
if (-not $python) { throw 'python.exe not found on PATH. Install Python 3.11+ (64-bit).' }
$pyVersion = & python.exe -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$pyVersion -lt [version]'3.11') {
    throw "Python $pyVersion found; the project requires 3.11 or newer."
}
Ok "python $pyVersion at $($python.Source)"

# IIS modules
$modules = Get-WebGlobalModule | Select-Object -ExpandProperty Name
if ($modules -notcontains 'httpPlatformHandler') {
    Warn 'httpPlatformHandler is NOT installed. The API site will not start.'
    Warn 'Install it: https://www.iis.net/downloads/microsoft/httpplatformhandler'
} else { Ok 'httpPlatformHandler present' }

if (-not $SkipFrontend -and ($modules -notcontains 'RewriteModule')) {
    Warn 'URL Rewrite is NOT installed. The SPA fallback rule will fail.'
    Warn 'Install it: https://www.iis.net/downloads/microsoft/url-rewrite'
} else { if (-not $SkipFrontend) { Ok 'URL Rewrite present' } }

# --- directories -----------------------------------------------------------
Say 'Creating directories'
foreach ($d in @($SiteRoot, (Join-Path $SiteRoot 'logs'))) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    Ok $d
}
if (-not $SkipFrontend) {
    if (-not (Test-Path $WebRoot)) { New-Item -ItemType Directory -Path $WebRoot -Force | Out-Null }
    Ok $WebRoot
}

# --- application files -----------------------------------------------------
Say 'Copying application files'
foreach ($item in @('app', 'migrations', 'alembic.ini', 'pyproject.toml',
                    'add_provider.py', 'clean_db.py', 'seed.py', 'show_counts.py')) {
    $src = Join-Path $backend $item
    if (Test-Path $src) {
        Copy-Item $src -Destination $SiteRoot -Recurse -Force
        Ok $item
    } else { Warn "$item not found, skipped" }
}

# --- virtualenv ------------------------------------------------------------
Say 'Creating virtualenv and installing dependencies'
$venv = Join-Path $SiteRoot 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    & python.exe -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
& $venvPy -m pip install --quiet --upgrade pip
Push-Location $SiteRoot
try {
    & $venvPy -m pip install --quiet -e "."
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
} finally { Pop-Location }

$installed = & $venvPy -c @"
import importlib
for m in ('fastapi','uvicorn','asyncpg','redis','pydantic','alembic','structlog','jose'):
    try:
        importlib.import_module(m); print(f'  {m}: ok')
    except Exception as e:
        print(f'  {m}: FAILED {e}')
"@
$installed | ForEach-Object { Write-Host $_ }
if ($installed -match 'FAILED') { throw 'A required package failed to import.' }
Ok 'dependencies installed'

# Note: uvloop is Linux-only. uvicorn[standard] excludes it on Windows via a
# platform marker, so uvicorn falls back to the asyncio event loop. Expected.

# --- migrations ------------------------------------------------------------
Say 'Running database migrations'
Push-Location $SiteRoot
try {
    $env:DATABASE_URL = $DatabaseUrl
    & $venvPy -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head failed. Check DATABASE_URL and that PostgreSQL is reachable."
    }
    $current = & $venvPy -m alembic current 2>&1
    Ok "alembic: $current"
} finally { Pop-Location }

# --- service provider row --------------------------------------------------
Say 'Registering the default service provider'
Push-Location $SiteRoot
try {
    $env:DATABASE_URL = $DatabaseUrl
    & $venvPy add_provider.py
    if ($LASTEXITCODE -ne 0) {
        Warn 'add_provider.py failed. Edge agents cannot ingest until it succeeds.'
    } else { Ok 'provider row present' }
} finally { Pop-Location }

# --- web.config ------------------------------------------------------------
Say 'Installing web.config for the API'
$targetCfg = Join-Path $SiteRoot 'web.config'
if (Test-Path $targetCfg) {
    Ok 'web.config already exists — left untouched'
} else {
    $srcCfg = Join-Path $PSScriptRoot 'web.config'
    if (-not (Test-Path $srcCfg)) { throw "web.config template not found beside this script." }
    $xml = Get-Content $srcCfg -Raw
    $xml = $xml.Replace('C:\inetpub\itdashboard-api', $SiteRoot)
    $xml = $xml.Replace('postgresql://hosp:CHANGE_ME@127.0.0.1:5432/hosp_prod', $DatabaseUrl)
    $xml = $xml.Replace('redis://127.0.0.1:6379', $RedisUrl)
    Set-Content -Path $targetCfg -Value $xml -Encoding UTF8
    Ok "wrote $targetCfg with your paths and connection strings"
}

# --- app pools -------------------------------------------------------------
Say 'Configuring application pools'

function Ensure-AppPool([string]$name) {
    if (-not (Test-Path "IIS:\AppPools\$name")) {
        New-WebAppPool -Name $name | Out-Null
        Ok "created app pool $name"
    } else { Ok "app pool $name exists" }
}

Ensure-AppPool $ApiAppPool
# No managed runtime — this is not a .NET app.
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name managedRuntimeVersion -Value ''
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name enable32BitAppOnWin64 -Value $false
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name startMode -Value 'AlwaysRunning'
# THE IMPORTANT TWO: the API runs a background outbox poller and holds SSE
# connections open. A recycle kills both.
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name processModel.idleTimeout -Value ([TimeSpan]::Zero)
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name recycling.periodicRestart.time -Value ([TimeSpan]::Zero)
Set-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name recycling.periodicRestart.requests -Value 0
Ok 'idle timeout and periodic recycle disabled'

if (-not $SkipFrontend) {
    Ensure-AppPool $WebAppPool
    Set-ItemProperty "IIS:\AppPools\$WebAppPool" -Name managedRuntimeVersion -Value ''
}

# --- permissions -----------------------------------------------------------
Say 'Granting the app pool identity access'
$apiIdentity = "IIS AppPool\$ApiAppPool"
foreach ($p in @($SiteRoot, (Join-Path $SiteRoot 'logs'))) {
    $acl = Get-Acl $p
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $apiIdentity, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.SetAccessRule($rule)
    Set-Acl -Path $p -AclObject $acl
    Ok "$apiIdentity -> Modify on $p"
}

# --- sites -----------------------------------------------------------------
Say 'Creating IIS sites'
if (-not (Get-Website -Name $ApiSiteName -ErrorAction SilentlyContinue)) {
    New-Website -Name $ApiSiteName -PhysicalPath $SiteRoot `
                -ApplicationPool $ApiAppPool -Port 8080 -Force | Out-Null
    Ok "created site $ApiSiteName on port 8080 (HTTP, for local testing only)"
    Warn 'Add an HTTPS binding with your certificate before exposing this.'
} else {
    Set-ItemProperty "IIS:\Sites\$ApiSiteName" -Name physicalPath -Value $SiteRoot
    Set-ItemProperty "IIS:\Sites\$ApiSiteName" -Name applicationPool -Value $ApiAppPool
    Ok "site $ApiSiteName updated"
}

# --- frontend --------------------------------------------------------------
if (-not $SkipFrontend) {
    Say 'Building the frontend'
    $frontend = Join-Path $RepoRoot 'frontend'
    if (-not (Test-Path (Join-Path $frontend 'package.json'))) {
        Warn "frontend\package.json not found — skipping the frontend build"
    } else {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Warn 'npm not found on PATH. Install Node 22+ or build the frontend elsewhere'
            Warn "and copy frontend\dist\* to $WebRoot."
        } else {
            Push-Location $frontend
            try {
                $env:VITE_API_BASE_URL     = $PublicUrl
                $env:VITE_APP_ENV          = 'production'
                $env:VITE_ENABLE_MSW       = 'false'
                $env:VITE_ENABLE_SIMULATION= 'false'
                $env:VITE_RELEASE_VERSION  = 'prod'
                & npm ci
                if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
                & npm run build:prod
                if ($LASTEXITCODE -ne 0) { throw 'npm run build:prod failed' }
                Ok "built with VITE_API_BASE_URL=$PublicUrl"
            } finally { Pop-Location }

            Say 'Deploying the frontend'
            $dist = Join-Path $frontend 'dist'
            Copy-Item (Join-Path $dist '*') -Destination $WebRoot -Recurse -Force
            $feCfg = Join-Path $WebRoot 'web.config'
            if (Test-Path $feCfg) {
                Ok 'frontend web.config already exists — left untouched'
            } else {
                Copy-Item (Join-Path $PSScriptRoot 'web.frontend.config') `
                          -Destination $feCfg -Force
                Ok "wrote $feCfg"
            }

            if (-not (Get-Website -Name $WebSiteName -ErrorAction SilentlyContinue)) {
                New-Website -Name $WebSiteName -PhysicalPath $WebRoot `
                            -ApplicationPool $WebAppPool -Port 8081 -Force | Out-Null
                Ok "created site $WebSiteName on port 8081 (HTTP, local testing only)"
            }
        }
    }
}

Say 'Done'
Write-Host @"

    NOT FINISHED YET. Remaining steps, in order:

    1. Bind HTTPS with your certificate, on the site(s) you just created:
         New-WebBinding -Name $ApiSiteName -Protocol https -Port 443 -HostHeader dashboard.yourdomain.com
       then assign the certificate in IIS Manager (Site Bindings -> Edit), or:
         Get-ChildItem Cert:\LocalMachine\My     # find the thumbprint
         New-Item IIS:\SslBindings\0.0.0.0!443 -Value <thumbprint>

    2. Verify the whole chain, including the SSE buffering check that is easy
       to miss:
         .\Test-ItDashboard.ps1 -BaseUrl $PublicUrl

    3. Point the edge agents' cloud_endpoint at:
         $PublicUrl/v1/edge/ingest

    Logs:
      $SiteRoot\logs\                      (uvicorn stdout + app logs)
      Get-WebSite; Get-WebAppPoolState $ApiAppPool
      Get-EventLog -LogName Application -Source "IIS*" -Newest 20

"@ -ForegroundColor Cyan
