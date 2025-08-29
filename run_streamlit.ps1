<#  run_streamlit.ps1
    Launches your Streamlit prototype with optional demo artifacts enabled.

    Usage examples:
      # Default: conda env "prototype", port 8501, demo OFF
      .\run_streamlit.ps1

      # Enable demo artifacts (synthetic), open headless, and auto-open Edge
      .\run_streamlit.ps1 -Demo -Headless -UseEdge

      # Custom env and port
      .\run_streamlit.ps1 -CondaEnv "mdaconda" -Port 8551 -Demo

    Notes:
      - Uses "conda run" (no fragile activate step).
      - DEMO_ARTIFACTS drives the Demo Artifacts expander in the app.
#>

[CmdletBinding()]
param(
  [string]$ProjectDir = "$PSScriptRoot",
  [string]$App        = "app_streamlit_audit.py",
  [string]$CondaEnv   = "prototype",
  [int]$Port          = 8501,
  [switch]$Demo,
  [switch]$Headless,
  [switch]$UseEdge
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Go to project directory
if (-not (Test-Path $ProjectDir)) { throw "ProjectDir not found: $ProjectDir" }
Set-Location $ProjectDir

if (-not (Test-Path $App)) { throw "App file not found: $App (expected in $ProjectDir)" }

# Demo toggle via environment
$env:DEMO_ARTIFACTS = if ($Demo) { "1" } else { "0" }

# Build Streamlit args
$streamlitArgs = @("run", $App, "--server.port", "$Port")
if ($Headless) { $streamlitArgs += @("--server.headless", "true") }

# Prefer conda run if available; otherwise fall back to current Python
$conda = Get-Command conda -ErrorAction SilentlyContinue
if ($conda) {
  Write-Host "Using conda env '$CondaEnv' via 'conda run'..."
  $cmd = "conda"
  $args = @("run","-n",$CondaEnv,"python","-m","streamlit") + $streamlitArgs
} else {
  Write-Warning "Conda not found in PATH. Falling back to 'python -m streamlit'. Ensure the correct environment is active."
  $cmd = "python"
  $args = @("-m","streamlit") + $streamlitArgs
}

Write-Host ""
Write-Host "Launching Streamlit..."
Write-Host "  Project: $ProjectDir"
Write-Host "  App:     $App"
Write-Host "  Port:    $Port"
Write-Host "  Demo:    $($Demo.IsPresent)"
Write-Host "  Headless:$($Headless.IsPresent)"
Write-Host ""

# Optionally open Edge to the app URL (useful with --headless)
$Url = "http://localhost:$Port"
if ($UseEdge) {
  try {
    Start-Process "msedge.exe" $Url
    Write-Host "Opening Microsoft Edge at $Url"
  } catch {
    Write-Warning "Could not start Edge automatically. You can open $Url manually."
  }
}

# Run Streamlit
& $cmd @args
