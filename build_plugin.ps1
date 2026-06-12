param(
  [string]$OutputDir = "..\..\dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = Join-Path $Root "plugins\recall"

Push-Location $PluginRoot
try {
  .\build_plugin.ps1 -OutputDir $OutputDir
} finally {
  Pop-Location
}
