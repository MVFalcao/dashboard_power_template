param(
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
  & $PythonExe -m pip install -e ".[dev]"
  & $PythonExe -m playwright install chromium
  & $PythonExe -m PyInstaller --noconfirm --clean --onefile --name dashboard-reporter --collect-data dashboard_reporter src/dashboard_reporter/__main__.py
}
finally {
  Pop-Location
}
