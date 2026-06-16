param(
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputPath = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $Root $OutputDir }
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $Python (Join-Path $Root "scripts\build_plugin.py") --plugin-root $Root --output-dir $OutputPath
if ($LASTEXITCODE -ne 0) {
  throw "RECALL build failed with exit code $LASTEXITCODE"
}
