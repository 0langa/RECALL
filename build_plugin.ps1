param(
  [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$ResolvedOutputDir = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $Root $OutputDir }
& $Python (Join-Path $Root "build_plugin.py") --output-dir $ResolvedOutputDir
if ($LASTEXITCODE -ne 0) {
  throw "RECALL build failed with exit code $LASTEXITCODE"
}
