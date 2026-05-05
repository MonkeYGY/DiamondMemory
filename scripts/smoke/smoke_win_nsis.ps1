Param(
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"

function Find-AppExePath {
  $roots = @()
  if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA "Programs") }
  if ($env:PROGRAMFILES) { $roots += $env:PROGRAMFILES }
  if (${env:ProgramFiles(x86)}) { $roots += ${env:ProgramFiles(x86)} }

  foreach ($root in $roots) {
    if (!(Test-Path $root)) { continue }

    $backendDirs = Get-ChildItem -Path $root -Recurse -Directory -Filter "backend" -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -like "*\resources\backend" }

    foreach ($backendDir in $backendDirs) {
      $resourcesDir = Split-Path -Parent $backendDir.FullName
      $installDir = Split-Path -Parent $resourcesDir

      $exe = Get-ChildItem -Path $installDir -File -Filter "*.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "Uninstall*" -and $_.Name -notlike "unins*" } |
        Select-Object -First 1

      if ($exe) { return $exe.FullName }
    }
  }

  return $null
}

if (!(Test-Path $InstallerPath)) {
  throw "InstallerPath not found: $InstallerPath"
}

Write-Host "Running NSIS installer (silent): $InstallerPath"
Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait
Start-Sleep -Seconds 2

$appExe = Find-AppExePath
if (!$appExe) {
  throw "Installed app exe not found"
}

Write-Host "Running smoke test: $appExe"
$projectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$smokeNode = Join-Path $projectDir "scripts\smoke\smoke_app.mjs"

node $smokeNode --app $appExe --timeout-sec $TimeoutSec

Write-Host "Windows NSIS smoke test completed"
