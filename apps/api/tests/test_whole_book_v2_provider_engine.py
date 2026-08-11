from __future__ import annotations

import json
import pytest

from app.model_gateway.base import ModelResponse
from app.narrative_core.whole_book_v2.contracts import (
    AssessmentSynthesisUnit, ChapterFunctionBatchUnit, CharactersSynthesisUnit,
    OverviewTypeSynthesisUnit, PacingCoreSynthesisUnit, StorySynthesisUnit,
    SuspenseSynthesisUnit, WholeBookAnalysisV2,
)
from app.narrative_core.whole_book_v2.engine import DeterministicPrimitiveExtractor, SourceChapter, WholeBookV2Engine
from app.narrative_core.whole_book_v2.provider_engine import CHAPTER_FUNCTION_BATCH_SIZE, GatewayWholeBookV2Analyzer, UnitFailureCode, recover_json_object
from app.narrative_core.whole_book_v2.runtime import ProviderUnitLedger

def source(count=3):
    return [SourceChapter(1000+i,i,f"chapter {i}",f"@Lin chapter {i} chooses a costly path and reveals clue {i}.",77,"rev") for i in range(1,count+1)]

def payloads(chapters):
    r=WholeBookV2Engine(DeterministicPrimitiveExtractor(),window_size=3,overlap=0).run(run_id=1,book_id=1,title="fixture",chapters=chapters)
    return [
        OverviewTypeSynthesisUnit(type_profile=r.type_profile,overview=r.overview).model_dump(mode="json"),
        StorySynthesisUnit(story=r.story).model_dump(mode="json"),
        CharactersSynthesisUnit(characters=r.characters).model_dump(mode="json"),
        SuspenseSynthesisUnit(suspense=r.suspense).model_dump(mode="json"),
        PacingCoreSynthesisUnit(pacing=r.pacing).model_dump(mode="json"),
        AssessmentSynthesisUnit(assessment=r.assessment).model_dump(mode="json"),
        # Chapter functions are requested last, in bounded batches (CHG-086).
        *[
            ChapterFunctionBatchUnit(
                functions=r.chapters.functions[i:i+CHAPTER_FUNCTION_BATCH_SIZE]
            ).model_dump(mode="json")
            for i in range(0,max(1,len(r.chapters.functions)),CHAPTER_FUNCTION_BATCH_SIZE)
        ],
    ]

class QueueGateway:
    def __init__(self,items):
        self.items=list(items)
        self.calls=[]
        # Legacy synthesis-only fixtures: keep deterministic window extract unless a test opts into Provider windows.
        self.deterministic_extraction=True
    async def generate(self,provider,request):
        self.calls.append((provider,request))
        item=self.items.pop(0)
        if isinstance(item,ModelResponse): return item
        return ModelResponse(text=json.dumps(item,ensure_ascii=False),model="fixture",finish_reason="stop",input_tokens=10,output_tokens=20)

def response(text,reason="stop"):
    return ModelResponse(text=text,model="fixture",finish_reason=reason,input_tokens=10,output_tokens=20)

def test_deterministic_json_recovery_normal_near_limit_truncated_and_missing_brace():
    normal='{"a":{"b":[1,2]}}'
    assert recover_json_object(normal)=={"a":{"b":[1,2]}}
    near='{"text":"' + ('x'*3990) + '"}'
    assert recover_json_object(near)["text"].endswith("x")
    assert recover_json_object(normal[:-1])=={"a":{"b":[1,2]}}
    assert recover_json_object('{"a":[1,2')=={"a":[1,2]}

@pytest.mark.asyncio
async def test_normal_units_merge_formal_result_evidence_progress_and_no_duplicates():
    chapters=source(); gateway=QueueGateway(payloads(chapters)); progress=[]
    analyzer=GatewayWholeBookV2Analyzer(gateway,provider_name="fake",model_name="fixture")
    result,responses=await analyzer.analyze(run_id=9,book_id=1,title="x",chapters=chapters,progress=lambda *x:progress.append(x))
    assert WholeBookAnalysisV2.model_validate_json(result.model_dump_json())==result
    assert len(gateway.calls)==7 and analyzer.stats.repair_calls==0
    assert len(result.chapters.functions)==len(chapters) and result.evidence_index
    assert progress[-1][0]=="materialize_report"
    # Complete resume reuses every successful unit and performs no provider call.
    result2,_=await analyzer.analyze(run_id=9,book_id=1,title="x",chapters=chapters)
    assert result2.story==result.story and len(gateway.calls)==7 and analyzer.stats.reused_units>=6
    assert analyzer.ledger.duplicate_provider_units==0
    assert analyzer.stats.window_calls>=1

@pytest.mark.asyncio
async def test_invalid_enum_repairs_failed_unit_only_and_reuses_partial_success():
    chapters=source(); good=payloads(chapters); invalid=json.loads(json.dumps(good[1])); invalid["story"]["storylines"][0]["status"]="bogus"
    # overview succeeds; story fails and is repaired; remaining units succeed.
    gateway=QueueGateway([good[0],invalid,good[1],*good[2:]])
    analyzer=GatewayWholeBookV2Analyzer(gateway,provider_name="fake",model_name="fixture")
    result,_=await analyzer.analyze(run_id=10,book_id=1,title="x",chapters=chapters)
    assert result.story.storylines[0].status!="bogus"
    assert len(gateway.calls)==8 and analyzer.stats.repair_calls==1
    assert analyzer.ledger.load("overview_type") is not None

@pytest.mark.asyncio
async def test_missing_field_and_truncated_unit_use_local_repair_only():
    chapters=source(); good=payloads(chapters)
    missing=json.loads(json.dumps(good[0])); del missing["overview"]["core_goal"]
    gateway=QueueGateway([missing,good[0],*good[1:]])
    analyzer=GatewayWholeBookV2Analyzer(gateway,provider_name="fake",model_name="fixture")
    await analyzer.analyze(run_id=11,book_id=1,title="x",chapters=chapters)
    assert analyzer.stats.repair_calls==1 and len(gateway.calls)==8

    raw=json.dumps(good[0],ensure_ascii=False)
    gateway2=QueueGateway([response(raw[:len(raw)//2],"length"),good[0],*good[1:]])
    analyzer2=GatewayWholeBookV2Analyzer(gateway2,provider_name="fake",model_name="fixture")
    await analyzer2.analyze(run_id=12,book_id=1,title="x",chapters=chapters)
    assert analyzer2.stats.repair_calls==1 and len(gateway2.calls)==8

@pytest.mark.asyncio
async def test_evidence_reference_invalid_repairs_only_unit():
    chapters=source(); good=payloads(chapters); bad=json.loads(json.dumps(good[3])); bad["suspense"]["lifecycles"][0]["evidence"]=["NOT-REAL"]
    gateway=QueueGateway([*good[:3],bad,good[3],*good[4:]])
    analyzer=GatewayWholeBookV2Analyzer(gateway,provider_name="fake",model_name="fixture")
    await analyzer.analyze(run_id=13,book_id=1,title="x",chapters=chapters)
    assert analyzer.stats.repair_calls==1 and len(gateway.calls)==8

@pytest.mark.asyncio
async def test_resume_with_partial_unit_ledger_calls_only_missing_units():
    chapters=source(); good=payloads(chapters); ledger=ProviderUnitLedger()
    ledger.save("overview_type",OverviewTypeSynthesisUnit.model_validate(good[0]))
    ledger.save("story",StorySynthesisUnit.model_validate(good[1]))
    gateway=QueueGateway(good[2:]); analyzer=GatewayWholeBookV2Analyzer(gateway,provider_name="fake",model_name="fixture",ledger=ledger)
    result,_=await analyzer.analyze(run_id=14,book_id=1,title="x",chapters=chapters)
    assert result.assessment.dimensions and len(gateway.calls)==5 and analyzer.stats.reused_units==2
