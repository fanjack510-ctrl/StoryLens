# DIAGNOSTIC ONLY — Run #11 Window 2075 with max_output_tokens=8192 (one Live call)
# Does NOT modify product defaults, formal DB, or build installers.
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$EvidenceDir = Join-Path $Repo "release\evidence\CHG-20260726-006\provider-window-2075-max8192"
$MeasurePy = Join-Path $EvidenceDir "measure_window_2075_max8192.py"
$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force $EvidenceDir | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    Write-Host "Stopping StoryLens: $($procs.Id -join ', ')"
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  $left = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($left) { throw "StoryLens still running: $($left.Id -join ', ')" }
  Write-Host "StoryLens closed: OK"
}

Assert-StoryLensClosed

if (-not (Test-Path -LiteralPath $FormalDb)) {
  throw "Formal DB not found: $FormalDb"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempRoot = Join-Path $env:TEMP "storylens-verify-p1-8192-$stamp"
$TempDb = Join-Path $TempRoot "storylens.db"
New-Item -ItemType Directory -Force $TempRoot | Out-Null

Write-Host "SQLite backup (read consistency) -> $TempDb"
& $Py -c @"
import sqlite3
from pathlib import Path
src = Path(r'''$FormalDb''')
dst = Path(r'''$TempDb''')
if dst.exists():
    dst.unlink()
s = sqlite3.connect(str(src))
try:
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
        d.commit()
    finally:
        d.close()
finally:
    s.close()
print('backup_ok')
"@
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed" }

# Pre-check alignment (no Provider call)
Write-Host "Precheck window 2075 alignment..."
$pre = & $Py -c @"
import json, hashlib, sqlite3
from pathlib import Path
con = sqlite3.connect(str(Path(r'''$TempDb''')))
con.row_factory = sqlite3.Row
w = dict(con.execute('SELECT * FROM whole_book_run_windows WHERE id=2075').fetchone())
assert w['run_id']==11 and w['window_index']==0
cp = json.loads(w['checkpoint_json'])
ids = cp['paragraph_ids']
rows = con.execute('SELECT id, raw_text FROM paragraphs WHERE id IN (%s)' % (','.join('?'*len(ids))), ids).fetchall()
by = {r['id']: r['raw_text'] for r in rows}
body = ''.join(by[i] for i in ids)
print(json.dumps({
  'window_id': w['id'],
  'paragraph_count': len(ids),
  'input_characters': len(body),
  'body_sha256': hashlib.sha256(body.encode()).hexdigest(),
}, ensure_ascii=False))
con.close()
"@
Write-Host $pre
$preObj = $pre | ConvertFrom-Json
if ([int]$preObj.paragraph_count -ne 40 -or [int]$preObj.input_characters -ne 576) {
  throw "Alignment failed: para=$($preObj.paragraph_count) chars=$($preObj.input_characters)"
}

Write-Host ""
Write-Host "=== REAL PROVIDER CALL WARNING ==="
Write-Host "About to call aliyun_qwen_plus / qwen3.7-plus ONCE"
Write-Host "max_output_tokens=8192  retry=0  cost_gate=CNY 0.50"
Write-Host "Formal DB will NOT be written. Product defaults will NOT be changed."
Write-Host "================================="
Write-Host ""

$env:PYTHONPATH = Join-Path $Repo "apps\api"
# Clear fake/live smoke switches; do not log keys
foreach ($k in @(
  "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE",
  "STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE_FAIL",
  "STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE"
)) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }

Push-Location $Repo
try {
  & $Py $MeasurePy $TempDb
  $code = $LASTEXITCODE
} finally {
  Pop-Location
}

Write-Host "MEASURE_EXIT=$code"
if (Test-Path (Join-Path $EvidenceDir "verification-summary.json")) {
  Get-Content (Join-Path $EvidenceDir "verification-summary.json") -Raw
}

# Ensure no leftover API server was started (this script does not start one)
exit $code
