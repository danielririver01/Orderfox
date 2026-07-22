param(
    [string]$TargetUrl = "http://localhost:5000",
    [string]$Slug = "velzia-stress",
    [switch]$Quick,
    [switch]$SkipZap,
    [switch]$SkipK6
)

$K6 = "C:\Program Files\k6\k6.exe"
$ReportDir = "tests/security/reports"
$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

Write-Host ""
Write-Host "================================" -ForegroundColor Magenta
Write-Host "  VELZIA - Security Audit Suite" -ForegroundColor Magenta
Write-Host "  Target: $TargetUrl" -ForegroundColor Magenta
Write-Host "================================" -ForegroundColor Magenta
Write-Host ""

$start = Get-Date

# Phase 1: k6 Security Checks
if (-not $SkipK6) {
    Write-Host "= Phase 1: k6 Security Checks (JWT, Headers) =" -ForegroundColor Cyan
    Write-Host ""

    # Headers
    Write-Host "  [1/4] Security Headers..." -NoNewline
    $tmpHdr = [System.IO.Path]::GetTempFileName()
    & $K6 run tests/security/audit-headers.js --quiet --env VELZIA_URL=$TargetUrl 2>$tmpHdr | Out-Null
    Write-Host " done" -ForegroundColor Green
    $hdrOutput = Get-Content $tmpHdr -Raw
    Remove-Item $tmpHdr -Force
    if ($hdrOutput.Trim()) { Write-Output $hdrOutput }

    # JWT
    Write-Host "  [2/4] JWT Audit..." -NoNewline
    $jwtOutput = & $K6 run tests/security/audit-jwt.js --quiet --env VELZIA_URL=$TargetUrl --env VELZIA_SLUG=$Slug 2>&1 | Out-String
    Write-Host " done" -ForegroundColor Green
    Write-Output $jwtOutput

    Write-Host ""
} else {
    Write-Host "= Phase 1: Skipped (-SkipK6) =" -ForegroundColor Gray
}

# Phase 2: OWASP ZAP Scan
if (-not $SkipZap) {
    Write-Host "= Phase 2: OWASP ZAP Scan =" -ForegroundColor Cyan
    Write-Host ""

    $zapRunning = $false
    try {
        $test = Invoke-RestMethod -Uri "http://localhost:8080/JSON/core/view/version/?apikey=velzia-audit-2026" -TimeoutSec 5
        $zapRunning = $true
        Write-Host "  ZAP connected (version: $($test.version))" -ForegroundColor Green
    } catch {
        Write-Host "  ZAP not running. Starting..." -ForegroundColor Yellow
        & ".\tests\security\zap-daemon.ps1" -Port 8080 -ApiKey "velzia-audit-2026"
    }

    $scanArgs = @{ }
    if ($Quick) { $scanArgs.QuickScan = $true } else { $scanArgs.ActiveScan = $true }

    $results = & ".\tests\security\zap-scan.ps1" -TargetUrl $TargetUrl -ApiKey "velzia-audit-2026" -ReportDir $ReportDir @scanArgs

    if ($results) {
        Write-Host ""
        Write-Host "  ZAP Results:" -ForegroundColor Cyan
        $hColor = if ($results.High -gt 0) { "Red" } else { "Green" }
        $mColor = if ($results.Medium -gt 0) { "Yellow" } else { "Green" }
        Write-Host "    High:     $($results.High)" -ForegroundColor $hColor
        Write-Host "    Medium:   $($results.Medium)" -ForegroundColor $mColor
        Write-Host "    Low:      $($results.Low)" -ForegroundColor Gray
        Write-Host "    Info:     $($results.Info)" -ForegroundColor Gray
        if ($results.ReportFile -and (Test-Path $results.ReportFile)) {
            Write-Host "    Report:   $($results.ReportFile)" -ForegroundColor Green
        }
    }
    Write-Host ""
} else {
    Write-Host "= Phase 2: Skipped (-SkipZap) =" -ForegroundColor Gray
}

# Final
$elapsed = [math]::Round(((Get-Date) - $start).TotalSeconds, 1)
Write-Host "================================" -ForegroundColor Magenta
Write-Host "  AUDIT COMPLETE" -ForegroundColor Magenta
Write-Host "  Time: ${elapsed}s" -ForegroundColor Magenta
Write-Host "================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Reports: $ReportDir" -ForegroundColor Cyan
