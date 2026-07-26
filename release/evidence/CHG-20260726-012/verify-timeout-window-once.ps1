# CHG-20260726-012 — Native Overview timeout 180s single-window Live verify
# Usage:
#   1) Preflight (no Provider call):
#      powershell -NoProfile -ExecutionPolicy Bypass -File "...\verify-timeout-window-once.ps1"
#   2) After reviewing printed values, confirm Live call:
#      powershell -NoProfile -ExecutionPolicy Bypass -File "...\verify-timeout-window-once.ps1" -ConfirmLive
param(
  [switch]$ConfirmLive
)
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$PrivateSrc = "D:\Dstorylens-private-engine-wt-phase2br1-integration\src"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260726-012"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
$Runner = Join-Path $Evidence "verify_timeout_window_once.py"
New-Item -ItemType Directory -Force $Evidence | Out-Null

function Assert-StoryLensClosed {
  $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($procs) {
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
  }
  $left = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -match '^(?i)storylens(-api|-desktop)?$'
  }
  if ($left) { throw "StoryLens still running — close installer app fully" }
}

Assert-StoryLensClosed

# Clear Fake gates
Get-ChildItem Env: | Where-Object {
  $_.Name -match 'FAKE' -and $_.Name -like 'STORYLENS_*'
} | ForEach-Object { Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue }
Remove-Item Env:STORYLENS_NATIVE_OVERVIEW_SMOKE_FAKE -ErrorAction SilentlyContinue
Remove-Item Env:STORYLENS_CHAPTER_ANALYSIS_SMOKE_FAKE -ErrorAction SilentlyContinue

$env:PYTHONPATH = (Join-Path $Repo "apps\api") + ";" + $PrivateSrc
$env:STORYLENS_APP_ENV = "production"

Write-Host "=== PART A: zero-cost parameter check ==="
$partA = & $Py -c @"
import json
from pathlib import Path
from typing import Any
import httpx
from app.model_gateway.base import ModelRequest, ModelResponse
from app.model_gateway.providers.openai_compatible import OpenAICompatibleProvider
from app.narrative_core.services.native_overview_live_transport import AliyunNativeOverviewTransport
from app.core.config import Settings

captured_providers: list[OpenAICompatibleProvider] = []
captured_reqs: list[ModelRequest] = []
_real_init = OpenAICompatibleProvider.__init__

def _init(self, *a, **k):
    _real_init(self, *a, **k)
    captured_providers.append(self)

async def fake_generate(self: Any, request: ModelRequest) -> ModelResponse:
    captured_reqs.append(request)
    return ModelResponse(
        text='{}', model=request.model or 'qwen3.7-plus', http_status_code=200,
        input_tokens=1, output_tokens=1, total_tokens=2, request_id='part-a', finish_reason='stop'
    )

class Store:
    def get(self, _n: str) -> str:
        return 'redacted-test-key'

import app.narrative_core.services.native_overview_live_transport as tmod
import app.services.aliyun_endpoint as ae
import app.services.cloud_pricing as cp
tmod.get_credential_store = lambda: Store()
ae.resolve_aliyun_compatible_base_url = lambda **k: 'https://example.invalid/v1'
cp.estimate_cost = lambda *a, **k: (0.0, 'CNY', 'test')
OpenAICompatibleProvider.__init__ = _init
OpenAICompatibleProvider.generate = fake_generate

assert AliyunNativeOverviewTransport.timeout_seconds == 180
assert AliyunNativeOverviewTransport.max_output_tokens == 8192
assert AliyunNativeOverviewTransport.max_auto_retries == 1

tr = AliyunNativeOverviewTransport(model='qwen3.7-plus', max_auto_retries=0)
# NO timeout / max_tokens override — product defaults
tr.request('part-a', {'stage': 'analyze_window'})
to = captured_providers[0]._timeout()
assert isinstance(to, httpx.Timeout)
settings = Settings()
out = {
  'native_timeout_seconds': AliyunNativeOverviewTransport.timeout_seconds,
  'httpx_connect': float(to.connect),
  'httpx_read': float(to.read),
  'httpx_write': float(to.write),
  'httpx_pool': float(to.pool),
  'max_output_tokens': AliyunNativeOverviewTransport.max_output_tokens,
  'max_auto_retries_class_default': AliyunNativeOverviewTransport.max_auto_retries,
  'aliyun_public_timeout_seconds': settings.aliyun_timeout_seconds,
  'local_llama_timeout_seconds': settings.local_llama_timeout_seconds,
  'real_provider_calls': 0,
  'passed': (
    AliyunNativeOverviewTransport.timeout_seconds == 180
    and float(to.connect) == 30.0
    and float(to.read) == 180.0
    and float(to.write) == 180.0
    and float(to.pool) == 30.0
    and AliyunNativeOverviewTransport.max_output_tokens == 8192
    and settings.aliyun_timeout_seconds == 300
  ),
}
Path(r'''$Evidence\part-a-parameter-check.json''').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False))
if not out['passed']:
    raise SystemExit(1)
"@
if ($LASTEXITCODE -ne 0) { throw "PART A FAILED" }
Write-Host "PART A PASS"
$partA | Tee-Object -FilePath (Join-Path $Evidence "test-results.txt") | Out-Null

Write-Host ""
Write-Host "=== PART B preflight / optional Live ==="
$argsList = @()
if ($ConfirmLive) { $argsList += "--confirm" }

& $Py $Runner @argsList
$code = $LASTEXITCODE

# Ensure no leftover uvicorn/python verification hang (script is sync and exits).
Write-Host "Runner exit=$code"

if (-not $ConfirmLive) {
  Write-Host ""
  Write-Host "Manual next step (user confirms after reviewing printed values):"
  Write-Host 'powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Dstorylens-wt-narrative-phase2br1-integration\release\evidence\CHG-20260726-012\verify-timeout-window-once.ps1" -ConfirmLive'
  exit 0
}

exit $code
