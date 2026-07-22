# ── Velzia Stress Test Suite — PowerShell Runner ──
param(
    [string]$Url = "http://localhost:5000",
    [string]$Email = "",
    [string]$Password = "",
    [string]$Slug = "demo",
    [switch]$Report
)

$K6 = "C:\Program Files\k6\k6.exe"
$Tests = @{
    "login"    = "tests/k6/login.js"
    "dashboard"= "tests/k6/dashboard.js"
    "products" = "tests/k6/products.js"
    "orders"   = "tests/k6/orders.js"
    "copilot"  = "tests/k6/copilot.js"
    "menu"     = "tests/k6/menu_public.js"
}

$EnvVars = "VELZIA_URL=$Url", "VELZIA_EMAIL=$Email", "VELZIA_PASSWORD=$Password", "VELZIA_SLUG=$Slug"
$Opts = @("--env", $EnvVars[0])
if ($Email) { $Opts += "--env"; $Opts += $EnvVars[1] }
if ($Password) { $Opts += "--env"; $Opts += $EnvVars[2] }
if ($Slug) { $Opts += "--env"; $Opts += $EnvVars[3] }

Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      VELZIA — Stress Test Suite          ║" -ForegroundColor Cyan
Write-Host "║      Target: $Url" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Runner (diagnóstico) ──
Write-Host "→ FASE 0: Diagnóstico general" -ForegroundColor Green
& $K6 run @Opts tests/k6/runner.js --quiet --summary-export tests/k6/reports/runner.json 2>&1 | Write-Host
Write-Host ""

# ── Phase 1: Survival ──
Write-Host "→ FASE 1: ¿Sobrevive? (5/10/20 usuarios)" -ForegroundColor Green
Write-Host "   5 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/full_restaurant.js --vus 5 --duration 30s --quiet --summary-export tests/k6/reports/phase1_5.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Green

Write-Host "   10 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/full_restaurant.js --vus 10 --duration 1m --quiet --summary-export tests/k6/reports/phase1_10.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Green

Write-Host "   20 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/full_restaurant.js --vus 20 --duration 1m --quiet --summary-export tests/k6/reports/phase1_20.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Green
Write-Host ""

# ── Phase 2: Load ──
Write-Host "→ FASE 2: Carga real (30 usuarios)" -ForegroundColor Yellow
Write-Host "   30 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/full_restaurant.js --vus 30 --duration 2m --quiet --summary-export tests/k6/reports/phase2_30.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Yellow
Write-Host ""

# ── Phase 3: Stress ──
Write-Host "→ FASE 3: Estrés progresivo (50/100/150)" -ForegroundColor Red
Write-Host "   50 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/full_restaurant.js --vus 50 --duration 2m --quiet --summary-export tests/k6/reports/phase3_50.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Red

Write-Host "   100 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/menu_public.js --vus 100 --duration 2m --quiet --summary-export tests/k6/reports/phase3_100.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Red

Write-Host "   150 usuarios..." -NoNewline
& $K6 run @Opts tests/k6/menu_public.js --vus 150 --duration 1m --quiet --summary-export tests/k6/reports/phase3_150.json 2>&1 | Out-Null
Write-Host " ✅" -ForegroundColor Red
Write-Host ""

# ── Report ──
if ($Report) {
    Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Magenta
    Write-Host "║           RESULTADOS RESUMEN              ║" -ForegroundColor Magenta
    Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Magenta
    Write-Host ""

    $files = @(
        @{Name = "Phase 1 (5 usuarios)"; File = "tests/k6/reports/phase1_5.json" },
        @{Name = "Phase 1 (10 usuarios)"; File = "tests/k6/reports/phase1_10.json" },
        @{Name = "Phase 1 (20 usuarios)"; File = "tests/k6/reports/phase1_20.json" },
        @{Name = "Phase 2 (30 usuarios)"; File = "tests/k6/reports/phase2_30.json" },
        @{Name = "Phase 3 (50 usuarios)"; File = "tests/k6/reports/phase3_50.json" },
        @{Name = "Phase 3 (100 usuarios)"; File = "tests/k6/reports/phase3_100.json" },
        @{Name = "Phase 3 (150 usuarios)"; File = "tests/k6/reports/phase3_150.json" }
    )

    foreach ($f in $files) {
        $path = Join-Path "$PSScriptRoot" $f.File
        if (Test-Path $path) {
            $data = Get-Content $path | ConvertFrom-Json
            $metrics = $data.metrics
            $p95 = if ($metrics.http_req_duration.'p(95)') { [math]::Round($metrics.http_req_duration.'p(95)', 1) } else { "N/A" }
            $avg = if ($metrics.http_req_duration.avg) { [math]::Round($metrics.http_req_duration.avg, 1) } else { "N/A" }
            $failRate = if ($metrics.http_req_failed.rate) { [math]::Round($metrics.http_req_failed.rate * 100, 2) } else { "N/A" }
            $reqs = if ($metrics.http_reqs.count) { $metrics.http_reqs.count } else { "N/A" }

            Write-Host ("{0,-25} | avg: {1,6}ms | p95: {2,6}ms | fails: {3,5}% | reqs: {4,5}" -f $f.Name, $avg, $p95, $failRate, $reqs)
        }
    }
}

Write-Host ""
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Reports saved to tests/k6/reports/" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
