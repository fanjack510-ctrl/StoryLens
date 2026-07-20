# StoryLens UI Audit runner (Windows PowerShell)
# Produces artifacts/StoryLens_UI_Audit_0.1.0.zip — does not push.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Root "apps\desktop\package.json"))) {
  $Root = (Get-Location).Path
}
if (-not (Test-Path (Join-Path $Root "apps\desktop\package.json"))) {
  throw "Cannot locate StoryLens repo root from $PSScriptRoot"
}

Write-Host "Repo: $Root"
Set-Location (Join-Path $Root "apps\desktop")

if (-not (Test-Path "node_modules")) {
  npm install
}

$work = Join-Path $Root "artifacts\ui-audit-work"
if (Test-Path $work) {
  Remove-Item -Recurse -Force $work
}
New-Item -ItemType Directory -Force -Path (Join-Path $work "screenshots") | Out-Null

Write-Host "Running Playwright UI audit..."
npx playwright test --config playwright.ui-audit.config.ts
if ($LASTEXITCODE -ne 0) {
  Write-Warning "Playwright exited with code $LASTEXITCODE — packing whatever screenshots exist."
}

Set-Location $Root
node (Join-Path $Root "scripts\ui-audit\pack-ui-audit.mjs")
Write-Host "Done. ZIP: $(Join-Path $Root 'artifacts\StoryLens_UI_Audit_0.1.0.zip')"
