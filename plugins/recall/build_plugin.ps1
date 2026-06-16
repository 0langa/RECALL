param(
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginName = "recall"
$Dist = Join-Path $Root $OutputDir
$Archive = Join-Path $Dist "$PluginName.zip"
$Python = "python"
$Validator = Join-Path $env:USERPROFILE ".codex\skills\.system\plugin-creator\scripts\validate_plugin.py"

function Invoke-Checked {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
  }
}

Push-Location $Root
try {
  Invoke-Checked $Python @("-m", "unittest", "discover", "-s", "tests")
  if (Test-Path $Validator) {
    Invoke-Checked $Python @($Validator, $Root)
  } else {
    Write-Warning "Plugin validator not found at $Validator; skipping validator gate."
  }
  Invoke-Checked $Python @(".\scripts\smoke_recall.py", "--json")
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
if (Test-Path $Archive) {
  Remove-Item $Archive
}

$Include = @(
  ".codex-plugin",
  "assets",
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
Invoke-Checked $Python @((Join-Path $Root "scripts\inspect_package.py"), $Archive)
Write-Host "Built $Archive"
