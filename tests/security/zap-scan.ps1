param(
    [string]$TargetUrl = "http://localhost:5000",
    [string]$ZapUrl = "http://localhost:8080",
    [string]$ApiKey = "velzia-audit-2026",
    [string]$ReportDir = "tests/security/reports",
    [switch]$ActiveScan,
    [switch]$QuickScan
)

$ErrorActionPrevention = "Stop"

function Invoke-ZapApi {
    param([string]$Endpoint, [string]$ExpectedProperty)
    $url = "$ZapUrl/JSON/$Endpoint/?apikey=$ApiKey"
    try {
        $resp = Invoke-RestMethod -Uri $url -TimeoutSec 300
        return $resp
    } catch {
        Write-Host "    ZAP API error: $_" -ForegroundColor Red
        return $null
    }
}

function Wait-ForScanToComplete {
    param([string]$ScanId, [string]$ScanType)
    $progressUrl = "$ZapUrl/JSON/$ScanType/view/status/?apikey=$ApiKey&scanId=$ScanId"
    do {
        Start-Sleep -Seconds 3
        $status = Invoke-RestMethod -Uri $progressUrl -TimeoutSec 10
        $pct = [int]$status.status
        Write-Progress -Activity "Escaneo $ScanType" -Status "$pct%" -PercentComplete $pct
    } while ($pct -lt 100)
    Write-Progress -Activity "Escaneo $ScanType" -Completed
}

# ── 1. Spider (rastreo) ──
Write-Host "  [1/4] Spider (rastreo de URLs)..." -ForegroundColor Cyan
$spider = Invoke-ZapApi "spider/action/scan/?url=$TargetUrl&maxChildren=5&recurse=true"
if ($spider -and $spider.scan) {
    Wait-ForScanToComplete -ScanId $spider.scan -ScanType "spider"
    Write-Host "     Spider completado!" -ForegroundColor Green
}

# ── 2. Passive Scan (automático, solo esperar) ──
Write-Host "  [2/4] Esperando escaneo pasivo..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
Write-Host "     Pasivo completado!" -ForegroundColor Green

# ── 3. Active Scan (opcional, más profundo) ──
if ($ActiveScan -or $QuickScan) {
    Write-Host "  [3/4] Active scan..." -ForegroundColor Cyan
    $active = Invoke-ZapApi "ascan/action/scan/?url=$TargetUrl&recurse=true&inScopeOnly=false"
    if ($active -and $active.scan) {
        Wait-ForScanToComplete -ScanId $active.scan -ScanType "ascan"
        Write-Host "     Active scan completado!" -ForegroundColor Green
    }
} else {
    Write-Host "  [3/4] Active scan omitido (usa -ActiveScan)" -ForegroundColor Gray
}

# ── 4. Alertas ──
Write-Host "  [4/4] Obteniendo alertas y generando reporte..." -ForegroundColor Cyan
$alerts = Invoke-ZapApi "core/view/alerts/?baseurl=$TargetUrl"

$high = 0; $medium = 0; $low = 0; $info = 0
if ($alerts -and $alerts.alerts) {
    foreach ($a in $alerts.alerts) {
        switch ($a.risk) {
            "High"   { $high++ }
            "Medium" { $medium++ }
            "Low"    { $low++ }
            "Informational" { $info++ }
        }
    }
}

Write-Host "     Alertas encontradas: High=$high Medium=$medium Low=$low Info=$info" -ForegroundColor $(if ($high -gt 0) {"Red"} elseif ($medium -gt 0) {"Yellow"} else {"Green"})

# ── Exportar reporte HTML ──
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
$reportFile = Join-Path $ReportDir "zap-report.html"
$reportUrl = "$ZapUrl/OTHER/core/other/htmlreport/?apikey=$ApiKey"
try {
    Invoke-WebRequest -Uri $reportUrl -OutFile $reportFile -TimeoutSec 30
    Write-Host "  Reporte HTML guardado: $reportFile" -ForegroundColor Green
} catch {
    Write-Host "  Error generando reporte: $_" -ForegroundColor Red
}

# ── Devolver resumen ──
return @{
    High = $high
    Medium = $medium
    Low = $low
    Info = $info
    ReportFile = $reportFile
}
