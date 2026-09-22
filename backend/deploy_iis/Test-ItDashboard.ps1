<#
.SYNOPSIS
    Verify an IIS deployment of the IT Dashboard cloud side.

.DESCRIPTION
    Eleven checks, PASS / WARN / FAIL each. Exit code is 0 only if nothing
    FAILED. The equivalent of the edge agents' preflight.py, for the cloud.

    Check 8 is the one that matters most: it proves Server-Sent Events are not
    being buffered by IIS. That failure is completely silent — the dashboard's
    live view just never updates, with no error in any log.

.PARAMETER BaseUrl
    The public HTTPS URL, e.g. https://dashboard.contoso.com

.PARAMETER SiteRoot
    Where the API is deployed. Default C:\inetpub\itdashboard-api

.PARAMETER ApiAppPool
    The API's application pool name. Default ItDashboardApi

.PARAMETER Provider
    The service_provider value to test ingest with. Default bluip

.PARAMETER SkipIngest
    Don't POST a synthetic batch (check 10).

.EXAMPLE
    .\Test-ItDashboard.ps1 -BaseUrl https://dashboard.contoso.com
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $BaseUrl,
    [string] $SiteRoot   = 'C:\inetpub\itdashboard-api',
    [string] $ApiAppPool = 'ItDashboardApi',
    [string] $Provider   = 'bluip',
    [int]    $SseTimeoutSeconds = 25,
    [switch] $SkipIngest
)

Set-StrictMode -Version Latest
$BaseUrl = $BaseUrl.TrimEnd('/')
$script:results = @()

function Report {
    param([string]$Name, [ValidateSet('PASS','FAIL','WARN')][string]$Status, [string]$Detail = '')
    $script:results += [pscustomobject]@{ Name = $Name; Status = $Status }
    $color = switch ($Status) { 'PASS' {'Green'} 'WARN' {'Yellow'} 'FAIL' {'Red'} }
    Write-Host ("  [{0}] {1}" -f $Status, $Name) -ForegroundColor $color
    if ($Detail) {
        foreach ($line in ($Detail -split "`n")) {
            if ($line.Trim()) { Write-Host "         $line" -ForegroundColor DarkGray }
        }
    }
}

Write-Host ("=" * 78)
Write-Host 'IT DASHBOARD - IIS DEPLOYMENT CHECK'
Write-Host ("=" * 78)
Write-Host "  base url : $BaseUrl"
Write-Host "  site root: $SiteRoot"
Write-Host ''

# --- 1. IIS modules --------------------------------------------------------
try {
    Import-Module WebAdministration -ErrorAction Stop
    $mods = Get-WebGlobalModule | Select-Object -ExpandProperty Name
    $missing = @()
    if ($mods -notcontains 'httpPlatformHandler') { $missing += 'httpPlatformHandler' }
    if ($mods -notcontains 'RewriteModule')       { $missing += 'URL Rewrite' }
    if ($missing.Count -eq 0) {
        Report '1. IIS modules installed' 'PASS' 'httpPlatformHandler, URL Rewrite'
    } else {
        Report '1. IIS modules installed' 'FAIL' ("missing: " + ($missing -join ', '))
    }
} catch {
    Report '1. IIS modules installed' 'WARN' "could not query IIS: $($_.Exception.Message)"
}

# --- 2. app pool will not recycle ------------------------------------------
try {
    $idle  = (Get-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name processModel.idleTimeout).Value
    $per   = (Get-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name recycling.periodicRestart.time).Value
    $reqs  = (Get-ItemProperty "IIS:\AppPools\$ApiAppPool" -Name recycling.periodicRestart.requests).Value
    $state = (Get-WebAppPoolState -Name $ApiAppPool).Value
    $bad = @()
    if ($idle -ne [TimeSpan]::Zero) { $bad += "idleTimeout=$idle (must be 00:00:00)" }
    if ($per  -ne [TimeSpan]::Zero) { $bad += "periodicRestart.time=$per (must be 00:00:00)" }
    if ($reqs -ne 0)                { $bad += "periodicRestart.requests=$reqs (must be 0)" }
    $detail = "state=$state idleTimeout=$idle periodicRestart=$per requests=$reqs"
    if ($bad.Count -eq 0) {
        Report '2. app pool will not recycle' 'PASS' $detail
    } else {
        Report '2. app pool will not recycle' 'FAIL' (
            ($bad -join "`n") +
            "`nA recycle kills the background outbox poller and every open SSE" +
            "`nconnection. Fix:" +
            "`n  Set-ItemProperty IIS:\AppPools\$ApiAppPool -Name processModel.idleTimeout -Value '00:00:00'" +
            "`n  Set-ItemProperty IIS:\AppPools\$ApiAppPool -Name recycling.periodicRestart.time -Value '00:00:00'")
    }
} catch {
    Report '2. app pool will not recycle' 'WARN' "could not read app pool '$ApiAppPool': $($_.Exception.Message)"
}

# --- 3. response buffering disabled in web.config --------------------------
$cfgPath = Join-Path $SiteRoot 'web.config'
try {
    if (-not (Test-Path $cfgPath)) {
        Report '3. web.config disables buffering' 'FAIL' "$cfgPath not found"
    } else {
        [xml]$cfg = Get-Content $cfgPath -Raw
        $handler = $cfg.configuration.'system.webServer'.handlers.add |
                   Where-Object { $_.modules -eq 'httpPlatformHandler' }
        $buf = if ($handler) { $handler.responseBufferLimit } else { $null }
        $dyn = $cfg.configuration.'system.webServer'.urlCompression.doDynamicCompression
        $problems = @()
        if ($buf -ne '0') { $problems += "responseBufferLimit='$buf' on the handler (must be 0)" }
        if ($dyn -eq 'true') { $problems += "doDynamicCompression=true (compression buffers SSE)" }
        if ($problems.Count -eq 0) {
            Report '3. web.config disables buffering' 'PASS' "responseBufferLimit=0, dynamic compression off"
        } else {
            Report '3. web.config disables buffering' 'FAIL' (
                ($problems -join "`n") +
                "`nWithout these, GET /v1/stream delivers nothing until the stream" +
                "`ncloses - which it never does. Check 8 confirms the live behaviour.")
        }
    }
} catch {
    Report '3. web.config disables buffering' 'WARN' "could not parse ${cfgPath}: $($_.Exception.Message)"
}

# --- 4. python environment -------------------------------------------------
$venvPy = Join-Path $SiteRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Report '4. virtualenv and dependencies' 'FAIL' "$venvPy not found"
} else {
    $probe = & $venvPy -c @"
import sys, importlib
print('python ' + sys.version.split()[0])
bad = []
for m in ('fastapi','uvicorn','asyncpg','redis','pydantic','pydantic_settings','alembic','structlog'):
    try: importlib.import_module(m)
    except Exception as e: bad.append(f'{m}: {e}')
print('MISSING:' + ('; '.join(bad) if bad else 'none'))
"@ 2>&1
    $joined = ($probe -join "`n")
    if ($joined -match 'MISSING:none') {
        Report '4. virtualenv and dependencies' 'PASS' $joined
    } else {
        Report '4. virtualenv and dependencies' 'FAIL' $joined
    }
}

# --- 5. database reachable and migrated ------------------------------------
if (Test-Path $venvPy) {
    Push-Location $SiteRoot
    try {
        $alembic = & $venvPy -m alembic current 2>&1
        $txt = ($alembic -join ' ')
        if ($LASTEXITCODE -eq 0 -and $txt -match '\(head\)') {
            Report '5. database migrated to head' 'PASS' $txt
        } elseif ($LASTEXITCODE -eq 0) {
            Report '5. database migrated to head' 'FAIL' (
                "$txt`nNot at head. Run: cd $SiteRoot; .\venv\Scripts\python.exe -m alembic upgrade head")
        } else {
            Report '5. database migrated to head' 'FAIL' (
                "$txt`nCould not reach the database. Check DATABASE_URL in web.config " +
                "and that the PostgreSQL service is running.")
        }
    } finally { Pop-Location }
} else {
    Report '5. database migrated to head' 'FAIL' 'skipped - no virtualenv'
}

# --- 6. Redis-compatible server reachable ----------------------------------
if (Test-Path $venvPy) {
    $redisUrl = $null
    try {
        if (Test-Path $cfgPath) {
            [xml]$cfg2 = Get-Content $cfgPath -Raw
            $ev = $cfg2.configuration.'system.webServer'.httpPlatform.environmentVariables.environmentVariable |
                  Where-Object { $_.name -eq 'REDIS_URL' }
            if ($ev) { $redisUrl = $ev.value }
        }
    } catch { }
    if (-not $redisUrl) { $redisUrl = 'redis://127.0.0.1:6379' }

    $rprobe = & $venvPy -c @"
import sys, asyncio
import redis.asyncio as aioredis
async def main():
    r = aioredis.from_url('$redisUrl', decode_responses=True)
    try:
        pong = await r.ping()
        info = {}
        try: info = await r.info('server')
        except Exception: pass
        name = info.get('redis_version') or info.get('memurai_version') or 'unknown'
        print(f'PING={pong} server_version={name}')
        # the app uses exactly these: get, setex, publish, pubsub
        await r.setex('itdash:selftest', 10, 'x')
        v = await r.get('itdash:selftest')
        n = await r.publish('itdash:selftest:chan', 'hello')
        print(f'setex/get ok (got {v!r}), publish returned {n}')
        print('OK')
    finally:
        await r.aclose()
asyncio.run(main())
"@ 2>&1
    $rtxt = ($rprobe -join "`n")
    if ($rtxt -match '(?m)^OK$') {
        Report '6. Redis-compatible server reachable' 'PASS' "$redisUrl`n$rtxt"
    } else {
        Report '6. Redis-compatible server reachable' 'FAIL' (
            "$redisUrl`n$rtxt`n" +
            "Redis has no official Windows build. The app needs only GET, SETEX,`n" +
            "PUBLISH and SUBSCRIBE - see IIS_DEPLOY.md section 3 for the options.")
    }
} else {
    Report '6. Redis-compatible server reachable' 'FAIL' 'skipped - no virtualenv'
}

# --- 7. the API answers through IIS ---------------------------------------
foreach ($probe in @(@{p='/livez'; n='7a. /livez through IIS'},
                     @{p='/readyz'; n='7b. /readyz (DB + Redis, as the app sees them)'})) {
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl$($probe.p)" -UseBasicParsing -TimeoutSec 20
        if ($r.StatusCode -eq 200) {
            Report $probe.n 'PASS' "HTTP 200 $($r.Content)"
        } else {
            Report $probe.n 'FAIL' "HTTP $($r.StatusCode) $($r.Content)"
        }
    } catch {
        $msg = $_.Exception.Message
        $resp = $null
        try { $resp = $_.Exception.Response } catch {}
        $code = if ($resp) { [int]$resp.StatusCode } else { 'no response' }
        Report $probe.n 'FAIL' (
            "$code - $msg`n" +
            "If this is a 502 the Python process failed to start: look in`n" +
            "$SiteRoot\logs\ for the uvicorn stdout log.")
    }
}

# --- 8. SSE IS NOT BUFFERED  (the check that catches the silent failure) ---
$sseName = '8. SSE not buffered by IIS'
try {
    Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
    $handler = New-Object System.Net.Http.HttpClientHandler
    $client  = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($SseTimeoutSeconds + 10)

    $req = New-Object System.Net.Http.HttpRequestMessage(
        [System.Net.Http.HttpMethod]::Get, "$BaseUrl/v1/stream")
    $req.Headers.Add('X-Provider-Id', $Provider)
    $req.Headers.Add('Accept', 'text/event-stream')

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $resp = $client.SendAsync($req,
        [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()

    if (-not $resp.IsSuccessStatusCode) {
        Report $sseName 'FAIL' "HTTP $([int]$resp.StatusCode) from /v1/stream"
    } else {
        $ctype = if ($resp.Content.Headers.ContentType) { $resp.Content.Headers.ContentType.ToString() } else { '' }
        $stream = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $buf = New-Object byte[] 512
        $readTask = $stream.ReadAsync($buf, 0, $buf.Length)
        $got = $readTask.Wait([TimeSpan]::FromSeconds($SseTimeoutSeconds))
        $sw.Stop()

        if ($got -and $readTask.Result -gt 0) {
            $text = [System.Text.Encoding]::UTF8.GetString($buf, 0, $readTask.Result)
            Report $sseName 'PASS' (
                "first bytes arrived after $([int]$sw.Elapsed.TotalMilliseconds) ms`n" +
                "content-type: $ctype`n" +
                "payload: $($text.Replace("`r",'').Replace("`n",' | ').Trim())")
        } else {
            Report $sseName 'FAIL' (
                "no bytes in $SseTimeoutSeconds s, but the connection is open.`n" +
                "This is response buffering. The stream never closes, so the`n" +
                "browser would receive nothing, forever, with no error anywhere.`n" +
                "Fix: responseBufferLimit='0' on the httpPlatformHandler entry in`n" +
                "web.config, and doDynamicCompression='false'. If you are using`n" +
                "ARR instead, also raise the ARR proxy timeout and disable`n" +
                "response buffering in the ARR proxy settings.")
        }
        try { $stream.Dispose() } catch {}
    }
    try { $resp.Dispose(); $client.Dispose() } catch {}
} catch {
    Report $sseName 'WARN' "could not test: $($_.Exception.Message)"
}

# --- 9. the frontend loads -------------------------------------------------
try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 20
    if ($r.StatusCode -eq 200 -and $r.Content -match '<div id="root"|<div id="app"|<script') {
        Report '9. dashboard UI loads' 'PASS' "HTTP 200, $($r.Content.Length) bytes"
    } else {
        Report '9. dashboard UI loads' 'WARN' "HTTP $($r.StatusCode), content did not look like the SPA shell"
    }
} catch {
    Report '9. dashboard UI loads' 'WARN' "could not load: $($_.Exception.Message)"
}

# --- 10. ingest accepts a batch (what the edge agents actually do) ---------
if ($SkipIngest) {
    Report '10. ingest accepts a batch' 'WARN' 'skipped (-SkipIngest)'
} else {
    $ts = [Math]::Floor((Get-Date -UFormat %s))
    $body = @{
        schema_version = '1.0'
        edge_id        = 'iis-smoke-test'
        service_provider = $Provider
        property_id    = '234'
        property_name  = 'IIS Smoke Test'
        messages = @(@{
            kind = 'edge_health'; ts = $ts
            metrics = @{ tracked_devices = 0; unhealthy_devices = 0
                         queue_depth = 0; summary_interval_seconds = 60 }
        })
    } | ConvertTo-Json -Depth 8

    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/v1/edge/ingest" -Method Post `
                -ContentType 'application/json' `
                -Headers @{ 'X-Provider-Id' = $Provider } `
                -Body $body -UseBasicParsing -TimeoutSec 25
        $ok = ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
        if ($ok -and $r.Content -match '"rejected"\s*:\s*\[\s*\]') {
            Report '10. ingest accepts a batch' 'PASS' (
                "HTTP $($r.StatusCode) $($r.Content)`n" +
                "A device named _edge:iis-smoke-test may now appear - remove it after testing.")
        } elseif ($ok) {
            Report '10. ingest accepts a batch' 'FAIL' "HTTP $($r.StatusCode) but messages were rejected: $($r.Content)"
        } else {
            Report '10. ingest accepts a batch' 'FAIL' "HTTP $($r.StatusCode) $($r.Content)"
        }
    } catch {
        $resp = $null
        try { $resp = $_.Exception.Response } catch {}
        $code = if ($resp) { [int]$resp.StatusCode } else { 0 }
        $hint = switch ($code) {
            401 { 'X-Provider-Id header rejected.' }
            422 { 'Payload shape rejected - compare with app\schemas\ingest.py.' }
            default {
                if ($code -ge 500) {
                    "Server error - most often the provider row is missing. Run:`n" +
                    "  cd $SiteRoot; .\venv\Scripts\python.exe add_provider.py"
                } else { $_.Exception.Message }
            }
        }
        Report '10. ingest accepts a batch' 'FAIL' "HTTP $code`n$hint"
    }
}

# --- 11. /docs is not public in production --------------------------------
try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/docs" -UseBasicParsing -TimeoutSec 15 `
            -ErrorAction SilentlyContinue
    if ($r -and $r.StatusCode -eq 200) {
        Report '11. Swagger /docs disabled' 'WARN' (
            "/docs returned 200 - ENVIRONMENT is probably not 'production'.`n" +
            "Set it in web.config and restart the app pool.")
    } else {
        Report '11. Swagger /docs disabled' 'PASS' "not served"
    }
} catch {
    Report '11. Swagger /docs disabled' 'PASS' 'not served (404)'
}

# --- summary ---------------------------------------------------------------
$pass = ($script:results | Where-Object Status -eq 'PASS').Count
$warn = ($script:results | Where-Object Status -eq 'WARN').Count
$fail = ($script:results | Where-Object Status -eq 'FAIL').Count

Write-Host ''
Write-Host ("=" * 78)
Write-Host "SUMMARY: $pass passed, $warn warnings, $fail failed"
if ($fail -gt 0) {
    Write-Host ''
    Write-Host 'FAILED:' -ForegroundColor Red
    $script:results | Where-Object Status -eq 'FAIL' | ForEach-Object {
        Write-Host "  - $($_.Name)" -ForegroundColor Red
    }
    Write-Host ''
    Write-Host 'Fix these before pointing any edge agent at this server.'
} else {
    Write-Host ''
    Write-Host 'Ready. Set each edge agent''s cloud_endpoint to:' -ForegroundColor Green
    Write-Host "  $BaseUrl/v1/edge/ingest" -ForegroundColor Green
}
Write-Host ("=" * 78)

exit $(if ($fail -gt 0) { 1 } else { 0 })
