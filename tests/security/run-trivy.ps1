param(
    [switch]$Quick,
    [switch]$Json,
    [switch]$Sarif
)

$trivy = "C:\Users\danie\AppData\Local\Microsoft\WinGet\Packages\AquaSecurity.Trivy_Microsoft.Winget.Source_8wekyb3d8bbwe\trivy.exe"
$reportDir = "C:\Users\danie\Desktop\Orderfox\tests\security\reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

if ($Quick) {
    # Config only (Dockerfile, IaC)
    & $trivy config -q --severity HIGH,CRITICAL .
} elseif ($Json) {
    & $trivy fs -q --severity HIGH,CRITICAL --scanners vuln --skip-dirs node_modules,.venv,.git --format json --output "$reportDir/trivy-fs.json" .
} elseif ($Sarif) {
    & $trivy config --severity HIGH,CRITICAL --format sarif --output "$reportDir/trivy-config.sarif" .
} else {
    # Full scan
    & $trivy config -q --severity HIGH,CRITICAL .
    Write-Host "`nFilesystem vulnerability scan..."
    & $trivy fs -q --severity HIGH,CRITICAL --scanners vuln --skip-dirs node_modules,.venv,.git .
}
