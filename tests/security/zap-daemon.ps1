param(
    [string]$Port = "8080",
    [string]$ApiKey = "velzia-audit-2026",
    [switch]$Stop
)

$ZapDir = "C:\Program Files\ZAP\Zed Attack Proxy"
$JavaDir = "C:\Program Files\Eclipse Adoptium\jre-17.0.19.10-hotspot\bin"

if ($Stop) {
    $proc = Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "zap" }
    if ($proc) {
        $proc | Stop-Process -Force
        Write-Host "ZAP daemon detenido" -ForegroundColor Yellow
    } else {
        Write-Host "ZAP no estaba corriendo" -ForegroundColor Gray
    }
    return
}

$procRunning = Get-Process -Name "java" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "zap" }
if ($procRunning) {
    Write-Host "ZAP ya está corriendo (PID: $($procRunning.Id))" -ForegroundColor Green
    return
}

Write-Host "Iniciando ZAP daemon en puerto $Port..." -ForegroundColor Cyan
Write-Host "  API Key: $ApiKey" -ForegroundColor Gray

$env:PATH = "$JavaDir;$env:PATH"

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "cmd.exe"
$psi.Arguments = "/c ""$ZapDir\zap.bat"" -daemon -port $Port -config api.key=$ApiKey -config api.addrs.addr.name=.* -config api.addrs.addr.regex=true"
$psi.WorkingDirectory = $ZapDir
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$procId = $proc.Id

Write-Host "  PID: $procId" -ForegroundColor Green
Write-Host "  Esperando a que ZAP termine de iniciar..." -ForegroundColor Gray

Start-Sleep -Seconds 15

# Verify it's running
$testUrl = "http://localhost:$Port/JSON/core/view/version/?apikey=$ApiKey"
try {
    $response = Invoke-RestMethod -Uri $testUrl -TimeoutSec 10
    Write-Host "  ZAP listo! Versión: $($response.version)" -ForegroundColor Green
} catch {
    Write-Host "  Esperando más tiempo..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    try {
        $response = Invoke-RestMethod -Uri $testUrl -TimeoutSec 10
        Write-Host "  ZAP listo! Versión: $($response.version)" -ForegroundColor Green
    } catch {
        Write-Host "  ERROR: No se pudo conectar con ZAP. Revisa los logs." -ForegroundColor Red
        Write-Host "  $_" -ForegroundColor Red
    }
}
