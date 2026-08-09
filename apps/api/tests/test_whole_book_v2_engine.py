from __future__ import annotations
import pytest
from pydantic import ValidationError
from app.narrative_core.whole_book_v2.contracts import EvidenceRef, SCHEMA_VERSION, V2_STAGES, WholeBookAnalysisV2
from app.narrative_core.whole_book_v2.engine import DeterministicPrimitiveExtractor, EvidenceValidator, SourceChapter, WholeBookV2Engine, build_provider_unit_plan, build_windows, merge_characters, Primitive, progress_snapshot
from app.narrative_core.whole_book_v2.runtime import ProviderUnitLedger, resolve_pinned_provider

def chapters(kind:str,count:int=36,missing:set[int]|None=None):
    missing=missing or set(); out=[]
    for i in range(1,count+1):
        if i in missing: continue
        motifs={"fantasy":"世界规则 身份线索 成长代价","mystery":"谜团 线索 误导 真相","relationship":"关系 选择 冲突 和解","degenerate":"重复","short":"短篇选择"}[kind]
        text=f"@林 @顾 第{i}章 {motifs}，人物作出选择并承担代价。"
        out.append(SourceChapter(1000+i,i,f"第{i}章",text,77,"rev-fixture"))
    return out

@pytest.mark.parametrize("kind",["fantasy","mystery","relationship"])
def test_three_genres_produce_complete_valid_v2_without_call_multiplication(kind):
    source=chapters(kind); extractor=DeterministicPrimitiveExtractor(); engine=WholeBookV2Engine(extractor,window_size=8,overlap=1)
    result=engine.run(run_id=9,book_id=3,title=kind,chapters=source)
    expected=len(build_windows(source,8,1))
    assert extractor.calls==expected
    assert result.schema_version==SCHEMA_VERSION
    assert WholeBookAnalysisV2.model_validate_json(result.model_dump_json())==result
    assert len(result.story.structure_stages)>=3
    assert result.characters.protagonist.stages[0].cost_paid
    assert len(result.characters.protagonist.external_status_track)==len(result.characters.protagonist.stages)
    assert result.suspense.lifecycles and result.pacing.points
    assert result.chapters.heatmap and len(result.assessment.dimensions)==6
    assert result.analysis_metadata.real_provider_calls==0

def test_short_missing_and_degenerate_sources_are_explicit_and_stable():
    for source in (chapters("short",3),chapters("mystery",12,{4,7}),chapters("degenerate",8)):
        result=WholeBookV2Engine(DeterministicPrimitiveExtractor(),window_size=4,overlap=1).run(run_id=2,book_id=1,title="edge",chapters=source)
        assert result.book_metadata.chapter_count==len(source)
        assert [c.chapter_id for c in result.chapters.functions]==[c.chapter_id for c in source]
    with pytest.raises(ValueError,match="chapters required"): build_windows([])

def test_evidence_identity_never_confuses_chapter_index_with_id():
    source=chapters("mystery",3); good=EvidenceRef(evidence_id="e",snapshot_id=77,revision_hash="rev-fixture",chapter_id=1001,chapter_index=1,chapter_title="第1章",start_offset=0,end_offset=2,quote_or_excerpt="@林",reason="test")
    EvidenceValidator(source).validate(good)
    with pytest.raises(ValueError,match="unknown chapter_id"): EvidenceValidator(source).validate(good.model_copy(update={"chapter_id":1}))
    with pytest.raises(ValueError,match="stale snapshot"): EvidenceValidator(source).validate(good.model_copy(update={"revision_hash":"old"}))
    with pytest.raises(ValidationError): EvidenceRef.model_validate({**good.model_dump(),"start_offset":5,"end_offset":2})

def test_alias_merge_is_not_exact_name_only():
    p1=Primitive(1,1,2,characters=["顾灯"],aliases={"顾灯":["顾大人","阿灯"]})
    p2=Primitive(2,3,4,characters=[" 顾大人 "])
    groups=merge_characters([p1,p2])
    assert len(groups)==1 and {"顾灯","顾大人","阿灯"}.issubset({x.strip() for x in next(iter(groups.values()))})

def test_provider_plan_is_shared_and_bounded():
    source=chapters("fantasy",129); plan=build_provider_unit_plan(source,window_size=20,input_rate=2,output_rate=4)
    assert plan.shared_extraction is True
    assert plan.window_units==7
    assert plan.estimated_calls < plan.window_units*7
    assert plan.estimated_tokens if False else plan.estimated_input_tokens>0

def test_progress_has_fifteen_real_stages_and_eta():
    assert len(V2_STAGES)==15
    p=progress_snapshot(stage_index=7,stage_percent=50,current_window=8,total_windows=20,current_chapter=400,total_chapters=1000,provider_calls_completed=8,provider_calls_estimated=28,provider="fake",model="fixture",elapsed=120,last_action="window 7",current_action="window 8")
    assert 49<=p.overall_percent<=51 and p.estimated_remaining_seconds>0
    assert p.current_action=="window 8" and p.last_activity_at.tzinfo

def test_pause_resume_ledger_has_no_duplicate_success_and_provider_is_pinned():
    ledger=ProviderUnitLedger(); calls=[]
    assert ledger.execute("window:1",lambda:calls.append(1) or {"ok":1})=={"ok":1}
    assert ledger.execute("window:1",lambda:calls.append(2))=={"ok":1}
    assert calls==[1] and ledger.duplicate_provider_units==ledger.duplicate_successful_assets==0
    assert resolve_pinned_provider(run_provider="deepseek",run_model="chat")==('deepseek','chat')
    with pytest.raises(ValueError,match="differs"): resolve_pinned_provider(run_provider="deepseek",run_model="chat",requested_provider="aliyun")

def test_formal_router_is_versioned_and_read_only(client):
    paths={r.path for r in client.app.routes}
    assert "/api/v1/whole-book-runs/{run_id}/v2" in paths
    response=client.get("/api/v1/whole-book-runs/999/v2")
    assert response.status_code==404 and response.json()["error_code"]=="WHOLE_BOOK_V2_RESULT_NOT_FOUND"
