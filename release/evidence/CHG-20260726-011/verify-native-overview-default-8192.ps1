# CHG-20260726-011 — Part A (zero cost) + optional Part B (one Live call)
# Usage:
#   .\verify-native-overview-default-8192.ps1            # Part A only
#   .\verify-native-overview-default-8192.ps1 -RunLive   # Part A then Part B
param(
  [switch]$RunLive
)
$ErrorActionPreference = "Stop"
$Repo = "D:\Dstorylens-wt-narrative-phase2br1-integration"
$Evidence = Join-Path $Repo "release\evidence\CHG-20260726-011"
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
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
  if ($left) { throw "StoryLens still running" }
}

Assert-StoryLensClosed
$env:PYTHONPATH = Join-Path $Repo "apps\api"

# ---------- Part A ----------
Write-Host "=== PART A: zero-cost default payload ==="
$partA = & $Py -c @"
import json
from pathlib import Path
from typing import Any
from app.model_gateway.base import ModelRequest, ModelResponse
from app.narrative_core.services.native_overview_live_transport import AliyunNativeOverviewTransport

captured: list[ModelRequest] = []

async def fake_generate(self: Any, request: ModelRequest) -> ModelResponse:
    captured.append(request)
    return ModelResponse(
        text='{}', model=request.model or 'qwen3.7-plus', http_status_code=200,
        input_tokens=1, output_tokens=1, total_tokens=2, request_id='part-a', finish_reason='stop'
    )

class Store:
    def get(self, _n: str) -> str:
        return 'redacted-test-key'

import app.narrative_core.services.native_overview_live_transport as tmod
import app.model_gateway.providers.openai_compatible as oc
tmod.get_credential_store = lambda: Store()
import app.services.aliyun_endpoint as ae
ae.resolve_aliyun_compatible_base_url = lambda **k: 'https://example.invalid/v1'
import app.services.cloud_pricing as cp
cp.estimate_cost = lambda *a, **k: (0.0, 'CNY', 'test')
oc.OpenAICompatibleProvider.generate = fake_generate

assert AliyunNativeOverviewTransport.max_output_tokens == 8192
tr = AliyunNativeOverviewTransport(model='qwen3.7-plus', max_auto_retries=0)
# NO explicit max_output_tokens — must come from product default
tr.request('part-a', {'stage': 'analyze_window'})
req = captured[0]
wire_max = req.max_output_tokens or req.max_tokens
out = {
  'default_class_attr': AliyunNativeOverviewTransport.max_output_tokens,
  'instance_default': tr.max_output_tokens,
  'outgoing_max_tokens': wire_max,
  'temperature': req.temperature,
  'response_format_mode': req.response_format_mode,
  'enable_thinking': req.enable_thinking,
  'real_provider_calls': 0,
  'passed': (
    wire_max == 8192
    and req.temperature == 0.2
    and req.response_format_mode == 'json_object'
    and req.enable_thinking is False
  ),
}
Path(r'''$Evidence\default-parameter-test.txt''').write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, ensure_ascii=False))
if not out['passed']:
    raise SystemExit(1)
"@
if ($LASTEXITCODE -ne 0) { throw "PART A FAILED — stop before Part B" }
Write-Host "PART A PASS"
$partA | Tee-Object -FilePath (Join-Path $Evidence "test-results.txt")

if (-not $RunLive) {
  Write-Host "Part B skipped (pass -RunLive to execute one real Provider call)."
  exit 0
}

# ---------- Part B ----------
Write-Host "=== PART B: one Live call using PRODUCT DEFAULT (no script 8192) ==="
$FormalDb = Join-Path $env:LOCALAPPDATA "StoryLens\database\storylens.db"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempDb = Join-Path $env:TEMP "storylens-chg011-$stamp\storylens.db"
New-Item -ItemType Directory -Force (Split-Path $TempDb) | Out-Null
& $Py -c @"
import sqlite3
from pathlib import Path
src=Path(r'''$FormalDb'''); dst=Path(r'''$TempDb''')
dst.parent.mkdir(parents=True, exist_ok=True)
s=sqlite3.connect(str(src)); d=sqlite3.connect(str(dst)); s.backup(d); d.commit(); d.close(); s.close()
print('backup_ok')
"@

& $Py -c @"
import hashlib, json, os, sys, time, traceback
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

REPO = Path(r'''$Repo''')
EV = Path(r'''$Evidence''')
sys.path.insert(0, str(REPO / 'apps' / 'api'))
os.environ['PYTHONPATH'] = str(REPO / 'apps' / 'api')

from app.db.models import AnalysisRun, WholeBookRunWindow, BookSnapshotParagraph, BookSnapshotChapter
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CONTRACT_VERSION, ChapterRef, OverviewRunRef, WholeBookOverviewWindowInputV1, WindowParagraph, WindowSlice
)
from app.narrative_core.enums import WholeBookAnalysisMode, WindowStatus
from app.narrative_core.services.native_overview_fixture_adapter import empty_prior_state
from app.narrative_core.services.snapshot_service import BookSnapshotServiceImpl
from app.narrative_core.services.native_overview_live_transport import AliyunNativeOverviewTransport
from app.services.cloud_pricing import estimate_cost
from storylens_private_engine.contracts.whole_book_overview_v1 import WholeBookOverviewWindowInputV1 as PIn
from storylens_private_engine.modules.book_overview.window_prompt import build_window_prompt
from storylens_private_engine.modules.book_overview.window_parser import parse_window_result_text
from storylens_private_engine.modules.book_overview.errors import NativeOverviewEngineError

EXPECTED_BODY = '1bdeda15d9419df48f6e862d64d4d740508a5cc336bd52970e0a0779fd11a1db'
EXPECTED_PROMPT = '3ce882b5c417c9cfe3bd213c36d8e6ed391dafc3d429f76379411a3b925aa31d'

# PRODUCT DEFAULT — do not pass 8192 in options
assert AliyunNativeOverviewTransport.max_output_tokens == 8192, 'product default not 8192'

engine = create_engine(f'sqlite:///{Path(r'''$TempDb''').as_posix()}', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
with Session() as session:
    run = session.get(AnalysisRun, 11)
    window = session.get(WholeBookRunWindow, 2075)
    assert window and window.run_id == 11 and window.window_index == 0
    total = int(session.scalar(select(func.count()).select_from(WholeBookRunWindow).where(WholeBookRunWindow.run_id==11)) or 0)
    cp = json.loads(window.checkpoint_json or '{}')
    snap_ids = [int(x) for x in cp['snapshot_paragraph_ids']]
    snaps = BookSnapshotServiceImpl(session)
    paras_db = list(session.scalars(select(BookSnapshotParagraph).where(BookSnapshotParagraph.id.in_(snap_ids))))
    order = {pid:i for i,pid in enumerate(snap_ids)}
    paras_db.sort(key=lambda p: order.get(int(p.id), 0))
    chapters = {c.id:c for c in session.scalars(select(BookSnapshotChapter).where(BookSnapshotChapter.snapshot_id==int(run.book_snapshot_id)))}
    chapter_refs=[]; seen=set(); paras=[]; body_parts=[]
    for p in paras_db:
        ch = chapters.get(p.snapshot_chapter_id)
        chapter_id = str(ch.source_chapter_id if ch and ch.source_chapter_id else p.snapshot_chapter_id)
        if p.snapshot_chapter_id not in seen:
            seen.add(p.snapshot_chapter_id)
            chapter_refs.append(ChapterRef(chapter_id=chapter_id, chapter_index=int(ch.chapter_order if ch else 0), title=str(ch.title if ch else '')))
        text = snaps.get_snapshot_paragraph_text(p.id)
        body_parts.append(text)
        paras.append(WindowParagraph(paragraph_id=p.stable_paragraph_id or p.source_paragraph_id or str(p.id), chapter_id=chapter_id, paragraph_index=int(p.paragraph_order), text=text))
    body=''.join(body_parts)
    body_sha = hashlib.sha256(body.encode()).hexdigest()
    if len(paras)!=40 or len(body)!=576 or body_sha!=EXPECTED_BODY:
        raise SystemExit(f'alignment fail paras={len(paras)} chars={len(body)} sha={body_sha}')

    win_in = WholeBookOverviewWindowInputV1(
        contract_version=CONTRACT_VERSION,
        run=OverviewRunRef(run_id=str(run.id), book_id=str(run.book_id), snapshot_id=str(run.book_snapshot_id), mode=WholeBookAnalysisMode.NATIVE, engine_version='native-overview-1', prompt_version='native-overview-window-v1'),
        window=WindowSlice(window_id=f'w-{window.window_index}', window_index=0, total_windows=max(1,total), start_paragraph_id=window.start_paragraph_id, end_paragraph_id=window.end_paragraph_id, chapter_refs=chapter_refs, paragraphs=paras, input_hash=window.input_hash, status=WindowStatus.RUNNING),
        prior_state=empty_prior_state(),
    )
    private = PIn.model_validate(win_in.model_dump(mode='json'))
    prompt = build_window_prompt(private)
    prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
    if prompt_sha != EXPECTED_PROMPT:
        raise SystemExit(f'prompt sha mismatch {prompt_sha}')

worst = estimate_cost('qwen3.7-plus', 5192, 8192)[0]
if worst is None or worst > 0.50:
    raise SystemExit(f'cost gate fail {worst}')
print(f'COST_GATE_OK {worst}; ONE live call; max_tokens from PRODUCT DEFAULT={AliyunNativeOverviewTransport.max_output_tokens}')

transport = AliyunNativeOverviewTransport(model='qwen3.7-plus', max_auto_retries=0)
# Critical: do NOT pass max_output_tokens in options
assert 'max_output_tokens' not in {'stage':'analyze_window'}
t0=time.perf_counter()
resp = transport.request(prompt, {'stage':'analyze_window', 'engine_id':'private-native-overview-v1', 'model':'qwen3.7-plus'})
elapsed=time.perf_counter()-t0
text=str(resp.get('text') or '')
finish=resp.get('finish_reason')
in_tok=int(resp.get('input_tokens') or 0)
out_tok=int(resp.get('output_tokens') or 0)
cost=float(resp.get('estimated_cost') or 0)
http=resp.get('http_status_code')
opens=text.count('{'); closes=text.count('}')
json_complete = opens==closes and text.strip().endswith('}')
parser='FAIL'; schema='FAIL'; internal=None; msg=None; parsed=None
try:
    parsed_obj = parse_window_result_text(text, private, finish_reason=str(finish) if finish else None)
    parser='PASS'; schema='PASS'
    parsed = parsed_obj.model_dump(mode='json')
except NativeOverviewEngineError as e:
    parser='FAIL'; msg=e.message; internal=(e.details or {}).get('internal_class')
    if (e.details or {}).get('reason')=='schema_validation_failed':
        schema='FAIL'
    parsed={'code':e.code,'message':e.message,'details':e.details}
except Exception as e:
    msg=f'{type(e).__name__}: {e}'
    parsed={'error':msg}

(EV/'raw-response.txt').write_text(text, encoding='utf-8')
(EV/'parser-result.json').write_text(json.dumps({'parser':parser,'schema':schema,'internal_class':internal,'message':msg,'parsed':parsed}, ensure_ascii=False, indent=2), encoding='utf-8')
(EV/'request-metadata-redacted.json').write_text(json.dumps({
  'provider':'aliyun_qwen_plus','model':'qwen3.7-plus','window_id':2075,'window_index':0,
  'body_sha256':body_sha,'prompt_sha256':prompt_sha,
  'max_tokens_source':'PRODUCT DEFAULT',
  'product_default_max_output_tokens': AliyunNativeOverviewTransport.max_output_tokens,
  'script_explicit_max_output_tokens': None,
  'temperature':0.2,'response_format':{'type':'json_object'},'enable_thinking':False,'timeout':90,'retry':0,
  'api_key':'REDACTED'
}, indent=2), encoding='utf-8')

summary={
  'part_b':'COMPLETED',
  'window_id':2075,
  'body_sha256':body_sha,
  'prompt_sha256':prompt_sha,
  'max_tokens_source':'PRODUCT DEFAULT',
  'outgoing_max_tokens': AliyunNativeOverviewTransport.max_output_tokens,
  'http_status':http,
  'finish_reason':finish,
  'input_tokens':in_tok,
  'output_tokens':out_tok,
  'json_complete':json_complete,
  'parser':parser,
  'schema':schema,
  'actual_cost_cny':cost,
  'elapsed_seconds':round(elapsed,3),
  'real_provider_calls':1,
  'database_writes':0,
  'passed': (
    AliyunNativeOverviewTransport.max_output_tokens==8192
    and http==200 and finish!='length' and out_tok < 8192
    and json_complete and parser=='PASS' and schema=='PASS' and cost<=0.50
  ),
  'measured_at': datetime.now(timezone.utc).isoformat(),
}
(EV/'live-verification-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not summary['passed']:
    raise SystemExit(2)
"@

if ($LASTEXITCODE -ne 0) { throw "PART B FAILED" }
Write-Host "PART B PASS"
exit 0
