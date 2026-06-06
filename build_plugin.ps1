param(
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginName = "recall"
$Dist = Join-Path $Root $OutputDir
$Archive = Join-Path $Dist "$PluginName.zip"

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
if (Test-Path $Archive) {
  Remove-Item $Archive
}

$Include = @(
  ".codex-plugin",
  "skills",
  "hooks",
  "scripts",
  "docs",
  "examples",
  "memory_config.template.json",
  "README.md",
  "CHANGELOG.md",
  "LICENSE"
)

$Temp = Join-Path $Dist "_package"
if (Test-Path $Temp) {
  Remove-Item -Recurse -Force $Temp
}
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

foreach ($Item in $Include) {
  $Source = Join-Path $Root $Item
  if (Test-Path $Source) {
    Copy-Item $Source -Destination $Temp -Recurse
  }
}

Get-ChildItem -Path $Temp -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path $Temp -Recurse -File -Filter "*.pyc" | Remove-Item -Force

Compress-Archive -Path (Join-Path $Temp "*") -DestinationPath $Archive
Remove-Item -Recurse -Force $Temp
Write-Host "Built $Archive"
