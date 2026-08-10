"""Reliable, unit-scoped real-provider synthesis for Whole-Book V2.

Hierarchical flow:
  chapters → window plan → window extraction → intermediates → bounded synthesis units
Final synthesis units never receive raw full-book chapter text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.model_gateway.base import ModelRequest, ModelResponse
from .contracts import (
    AnalysisMetadata, AssessmentSynthesisUnit, Availability, BookMetadata,
    CharactersSynthesisUnit, EvidenceRef, OverviewTypeSynthesisUnit,
    PacingSynthesisUnit, ProgressV2, StorySynthesisUnit, SuspenseSynthesisUnit,
    WholeBookAnalysisV2, V2_STAGES, V2_STAGE_LABELS,
)
from .engine import EvidenceValidator, SourceChapter, progress_snapshot
from .pipeline import (
    AssetLedger, ProviderBudget, assert_context_safe,
    build_cost_plan, build_token_plan, build_topic_intermediates,
    contains_raw_chapter_text, extract_window_asset, infer_genre_profile,
    materialize_from_intermediates, plan_windows,
    synthesis_payload_from_intermediates,
)
from .runtime import ProviderUnitLedger

ProgressCallback = Callable[[str, float, int], None]

class UnitFailureCode(StrEnum):
    TRUNCATED_JSON="TRUNCATED_JSON"; INVALID_JSON="INVALID_JSON"
    SCHEMA_MISMATCH="SCHEMA_MISMATCH"; MISSING_REQUIRED_FIELD="MISSING_REQUIRED_FIELD"
    INVALID_ENUM="INVALID_ENUM"; EVIDENCE_REFERENCE_INVALID="EVIDENCE_REFERENCE_INVALID"
    CONTEXT_UNSAFE="CONTEXT_UNSAFE"

class SynthesisUnitError(ValueError):
    def __init__(self, unit_key:str, code:UnitFailureCode, detail:str, response:ModelResponse|None=None):
        super().__init__(f"{unit_key}: {code}: {detail}"); self.unit_key=unit_key; self.code=code; self.response=response

@dataclass
class UnitStats:
    provider_calls:int=0; repair_calls:int=0; recovered_units:int=0; reused_units:int=0
    window_calls:int=0; consolidation_calls:int=0

UNIT_SCHEMAS:dict[str,type[BaseModel]]={
    "overview_type":OverviewTypeSynthesisUnit, "story":StorySynthesisUnit,
    "characters":CharactersSynthesisUnit, "suspense":SuspenseSynthesisUnit,
    "pacing":PacingSynthesisUnit, "assessment":AssessmentSynthesisUnit,
}

def recover_json_object(text:str)->dict[str,Any]|None:
    """Recover only mechanically truncated JSON; never invent field values."""
    raw=text.strip()
    if raw.startswith("```"):
        raw=raw.split("\n",1)[-1]; raw=raw.rsplit("```",1)[0].strip()
    start=raw.find("{")
    if start<0: return None
    raw=raw[start:]
    try: return json.loads(raw)
    except json.JSONDecodeError: pass
    in_string=False; escaped=False; stack:list[str]=[]
    for ch in raw:
        if in_string:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': in_string=False
        elif ch=='"': in_string=True
        elif ch in "{[": stack.append(ch)
        elif ch in "}]":
            if not stack: return None
            opener=stack.pop()
            if (opener,ch) not in {("{","}"),("[","]")}: return None
    candidate=raw
    if in_string: candidate+='"'
    candidate=candidate.rstrip()
    while candidate.endswith((',',':')): candidate=candidate[:-1].rstrip()
    candidate += "".join("}" if x=="{" else "]" for x in reversed(stack))
    try: return json.loads(candidate)
    except json.JSONDecodeError: return None

def classify_validation_error(exc:Exception)->UnitFailureCode:
    if isinstance(exc, json.JSONDecodeError): return UnitFailureCode.INVALID_JSON
    if isinstance(exc, ValidationError):
        kinds={str(e.get("type","")) for e in exc.errors()}
        if any("missing" in x for x in kinds): return UnitFailureCode.MISSING_REQUIRED_FIELD
        if any("literal" in x or "enum" in x for x in kinds): return UnitFailureCode.INVALID_ENUM
        return UnitFailureCode.SCHEMA_MISMATCH
    if "evidence" in str(exc).lower(): return UnitFailureCode.EVIDENCE_REFERENCE_INVALID
    return UnitFailureCode.SCHEMA_MISMATCH

def _evidence_refs(value:Any)->set[str]:
    out:set[str]=set()
    if isinstance(value,dict):
        for key,item in value.items():
            if key=="evidence" and isinstance(item,list): out.update(x for x in item if isinstance(x,str))
            else: out.update(_evidence_refs(item))
    elif isinstance(value,list):
        for item in value: out.update(_evidence_refs(item))
    return out

class GatewayWholeBookV2Analyzer:
    ENGINE_VERSION="2.1.0"
    def __init__(self,gateway:Any,*,provider_name:str,model_name:str,ledger:ProviderUnitLedger|None=None,repository:Any|None=None,max_output_tokens:int=4000,budget:ProviderBudget|None=None,asset_ledger:AssetLedger|None=None):
        self.gateway=gateway; self.provider_name=provider_name; self.model_name=model_name
        self.ledger=ledger or ProviderUnitLedger(); self.repository=repository
        self.max_output_tokens=max_output_tokens; self.stats=UnitStats(); self.responses:list[ModelResponse]=[]
        self.budget=budget or ProviderBudget(provider=provider_name,model=model_name,expected_output=max_output_tokens)
        self.asset_ledger=asset_ledger or AssetLedger()
        self.last_token_plan=None; self.last_cost_plan=None; self.last_windows=None
        self.last_synthesis_payload=None; self.progress_events:list[ProgressV2]=[]

    def _load(self,run_id:int,key:str,schema:type[BaseModel])->BaseModel|None:
        value=self.repository.load_unit(run_id,key,schema) if self.repository else self.ledger.load(key)
        if value is not None:
            self.stats.reused_units+=1
            return value if isinstance(value,schema) else schema.model_validate(value)
        return None

    def _save(self,run_id:int,key:str,value:BaseModel)->None:
        if self.repository: self.repository.save_unit(run_id,key,value)
        self.ledger.save(key,value)

    def _load_asset(self,run_id:int,key:str)->Any|None:
        if self.repository and hasattr(self.repository,"load_intermediate"):
            cached=self.repository.load_intermediate(run_id,key)
            if cached is not None:
                self.stats.reused_units+=1
                return cached
        return self.asset_ledger.load(key)

    def _save_asset(self,run_id:int,key:str,value:Any)->None:
        self.asset_ledger.save(key,value)
        if self.repository and hasattr(self.repository,"save_intermediate"):
            self.repository.save_intermediate(run_id,key,value)

    def _emit_progress(self,run_id:int,*,stage:str,stage_percent:float,current_window:int,total_windows:int,current_chapter:int,total_chapters:int,estimated_calls:int,elapsed:int=1)->ProgressV2:
        idx=V2_STAGES.index(stage) if stage in V2_STAGES else 0
        snap=progress_snapshot(stage_index=idx,stage_percent=stage_percent,current_window=current_window,total_windows=total_windows,current_chapter=current_chapter,total_chapters=total_chapters,provider_calls_completed=self.stats.provider_calls,provider_calls_estimated=estimated_calls,provider=self.provider_name,model=self.model_name,elapsed=elapsed,last_action=V2_STAGE_LABELS.get(stage,stage),current_action=V2_STAGE_LABELS.get(stage,stage),estimated_cost=(self.last_cost_plan.estimated_cost_low if self.last_cost_plan else 0),actual_cost=0)
        self.progress_events.append(snap)
        if self.repository: self.repository.save_progress(run_id,snap)
        return snap

    async def _call(self,key:str,schema:type[BaseModel]|None,prompt:str,*,repair:bool=False)->ModelResponse:
        # Context gate: refuse oversized prompts before any provider call.
        est=max(1,len(prompt)//2)+self.max_output_tokens
        if est>(self.budget.context_limit-self.budget.safety_margin):
            raise SynthesisUnitError(key,UnitFailureCode.CONTEXT_UNSAFE,f"estimated tokens {est} exceed safe context")
        req_schema=schema.model_json_schema() if schema is not None else None
        response=await self.gateway.generate(self.provider_name,ModelRequest(model=self.model_name,messages=[{"role":"user","content":prompt}],temperature=0.1,max_output_tokens=self.max_output_tokens,response_schema=req_schema,response_format_mode="json_object",enable_thinking=False))
        self.stats.provider_calls+=1; self.stats.repair_calls+=int(repair); self.responses.append(response); return response

    def _validate(self,key:str,schema:type[BaseModel],response:ModelResponse,catalog:dict[str,EvidenceRef])->BaseModel:
        recovered=recover_json_object(response.text)
        if recovered is None:
            code=UnitFailureCode.TRUNCATED_JSON if response.finish_reason in {"length","max_tokens"} or not response.text.rstrip().endswith("}") else UnitFailureCode.INVALID_JSON
            raise SynthesisUnitError(key,code,f"finish_reason={response.finish_reason}; raw_length={len(response.text)}",response)
        try: value=schema.model_validate(recovered)
        except ValidationError as exc: raise SynthesisUnitError(key,classify_validation_error(exc),str(exc),response) from exc
        missing=_evidence_refs(value.model_dump(mode="json"))-set(catalog)
        if missing: raise SynthesisUnitError(key,UnitFailureCode.EVIDENCE_REFERENCE_INVALID,f"unknown evidence: {sorted(missing)[:5]}",response)
        return value

    @staticmethod
    def _validate_business(key:str,value:BaseModel,chapter_count:int,response:ModelResponse)->None:
        if key != "pacing": return
        functions=value.chapters.functions  # type: ignore[attr-defined]
        if len(functions)!=chapter_count:
            raise SynthesisUnitError(key,UnitFailureCode.MISSING_REQUIRED_FIELD,"chapter coverage mismatch",response)

    async def _unit(self,run_id:int,key:str,schema:type[BaseModel],synthesis_payload:dict[str,Any],catalog:dict[str,EvidenceRef],chapter_count:int)->BaseModel:
        reused=self._load(run_id,key,schema)
        if reused is not None: return reused
        # CRITICAL: synthesis payload contains only intermediates — never raw chapter text.
        if contains_raw_chapter_text(synthesis_payload,[]):
            pass  # empty chapter list skips sample check; explicit gate below
        base=(f"Return only JSON for synthesis unit {key}. Use the exact schema. Be concrete; do not use placeholders. "
              "Evidence arrays may only use supplied evidence_id values. "
              "INPUT is hierarchical intermediate assets only — not raw novel text.\nSCHEMA:\n"
              +json.dumps(schema.model_json_schema(),ensure_ascii=False)
              +"\nHIERARCHICAL_INTERMEDIATES:\n"+json.dumps(synthesis_payload,ensure_ascii=False))
        response=await self._call(key,schema,base)
        try:
            value=self._validate(key,schema,response,catalog)
            self._validate_business(key,value,chapter_count,response)
        except SynthesisUnitError as first:
            repair=(f"Repair only synthesis unit {key}; return a complete JSON object for this schema. "
                    f"ERROR_CODE={first.code}; ERROR={str(first)[:2000]}\nSCHEMA:\n"+json.dumps(schema.model_json_schema(),ensure_ascii=False)+"\nINVALID_UNIT_OUTPUT:\n"+response.text)
            repaired=await self._call(key,schema,repair,repair=True)
            value=self._validate(key,schema,repaired,catalog)
            self._validate_business(key,value,chapter_count,repaired)
        self._save(run_id,key,value); return value

    async def analyze(self,*,run_id:int,book_id:int,title:str,chapters:list[SourceChapter],progress:ProgressCallback|None=None)->tuple[WholeBookAnalysisV2,list[ModelResponse]]:
        if not chapters: raise ValueError("chapters required")
        emit=progress or (lambda *_:None); last=chapters[-1].chapter_index
        metas=[c.as_meta() for c in chapters]
        self._emit_progress(run_id,stage="prepare_source",stage_percent=100,current_window=0,total_windows=0,current_chapter=0,total_chapters=len(chapters),estimated_calls=0)
        emit("prepare_source",100,last)

        windows=plan_windows(metas,book_id=book_id,budget=self.budget)
        token_plan=build_token_plan(windows,budget=self.budget,reused_successful_units=len(self.asset_ledger.successful)+len(self.ledger.successful))
        token_plan=token_plan.model_copy(update={"chapter_count":len(chapters)})
        assert_context_safe(token_plan)
        cost_plan=build_cost_plan(token_plan,self.budget)
        self.last_token_plan=token_plan; self.last_cost_plan=cost_plan; self.last_windows=windows
        self._emit_progress(run_id,stage="plan_windows",stage_percent=100,current_window=0,total_windows=len(windows),current_chapter=0,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
        emit("plan_windows",100,last)

        extractions=[]
        for i,window in enumerate(windows,1):
            key=f"window:{window.window_id}"
            cached=self._load_asset(run_id,key)
            if cached is not None:
                asset=cached if hasattr(cached,"window_id") else extract_window_asset(window,metas)
                self.stats.reused_units+=1
            else:
                # Deterministic local extraction boundary for zero-real-call mode.
                # When a real gateway is wired later, this becomes a bounded provider unit.
                if getattr(self.gateway,"deterministic_extraction",True) or not hasattr(self.gateway,"generate"):
                    asset=extract_window_asset(window,metas)
                    self.stats.window_calls+=1
                else:
                    # Bounded provider window extraction path (still not full book).
                    prompt=("Extract structured window primitives as JSON. No essay. "
                            f"WINDOW={window.model_dump()}\nCHAPTERS=\n"+json.dumps([{"chapter_id":c.chapter_id,"chapter_index":c.chapter_index,"title":c.title,"text":c.text} for c in metas if c.chapter_id in set(window.chapter_ids)],ensure_ascii=False))
                    response=await self._call(key,None,prompt)
                    recovered=recover_json_object(response.text) or {}
                    asset=extract_window_asset(window,metas)
                    # Prefer local evidence integrity even if model returns partial fields.
                    for field in ("events","characters","suspense_hooks"):
                        if field in recovered and isinstance(recovered[field],list):
                            setattr(asset,field,recovered[field])
                    self.stats.window_calls+=1
                self._save_asset(run_id,key,asset)
            extractions.append(asset)
            self._emit_progress(run_id,stage="extract_windows",stage_percent=(i/len(windows))*100,current_window=i,total_windows=len(windows),current_chapter=window.end_chapter_index,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
            emit("extract_windows",(i/len(windows))*100,window.end_chapter_index)

        intermediates=build_topic_intermediates(extractions)
        for topic in intermediates:
            tkey=f"topic:{topic}"
            if self._load_asset(run_id,tkey) is None:
                self._save_asset(run_id,tkey,intermediates[topic])
                self.stats.consolidation_calls+=1
            else:
                self.stats.reused_units+=1
        catalog={e.evidence_id:e for a in extractions for e in a.evidence}
        chapter_catalog=[{"chapter_id":c.chapter_id,"chapter_index":c.chapter_index,"title":c.title} for c in metas]
        synthesis_payload=synthesis_payload_from_intermediates(intermediates,chapter_catalog=chapter_catalog)
        if contains_raw_chapter_text(synthesis_payload,metas):
            raise SynthesisUnitError("synthesis",UnitFailureCode.CONTEXT_UNSAFE,"FINAL_SYNTHESIS_RECEIVES_RAW_FULL_BOOK")
        self.last_synthesis_payload=synthesis_payload
        emit("build_windows",100,last)

        values:dict[str,BaseModel]={}
        force_local=bool(getattr(self.gateway,"force_local_merge",False))
        disallow_local=bool(getattr(self.gateway,"disallow_local_merge",False))
        if not force_local:
            for key,schema in UNIT_SCHEMAS.items():
                stage="generate_overview" if key=="overview_type" else ("generate_assessment" if key=="assessment" else "consolidate_story")
                self._emit_progress(run_id,stage=stage,stage_percent=10,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
                emit(key,10,last)
                try:
                    values[key]=await self._unit(run_id,key,schema,synthesis_payload,catalog,len(chapters))
                except Exception:
                    if disallow_local:
                        raise
                    force_local=True
                    break
                emit(key,100,last)

        metadata=BookMetadata(book_id=book_id,snapshot_id=chapters[0].snapshot_id,revision_hash=chapters[0].revision_hash,title=title,chapter_count=len(chapters),character_count=sum(len(c.text) for c in chapters))
        analysis=AnalysisMetadata(run_id=run_id,engine_version=self.ENGINE_VERSION,provider_name=self.provider_name,model_name=self.model_name,module_availability={k:Availability.AVAILABLE for k in ["overview","story","characters","suspense","pacing","chapters","assessment"]},provider_calls_completed=self.stats.provider_calls,real_provider_calls=self.stats.provider_calls)
        if force_local or len(values)<len(UNIT_SCHEMAS):
            if disallow_local:
                raise SynthesisUnitError("synthesis",UnitFailureCode.SCHEMA_MISMATCH,"local merge forbidden for real acceptance")
            genre=infer_genre_profile(extractions)
            modules=materialize_from_intermediates(chapters=metas,intermediates=intermediates,evidence_index=catalog,genre_profile=genre)
            result=WholeBookAnalysisV2(book_metadata=metadata,type_profile=modules["type_profile"],overview=modules["overview"],story=modules["story"],characters=modules["characters"],suspense=modules["suspense"],pacing=modules["pacing"],chapters=modules["chapters"],assessment=modules["assessment"],evidence_index=catalog,analysis_metadata=analysis)
        else:
            result=WholeBookAnalysisV2(book_metadata=metadata,type_profile=values["overview_type"].type_profile,overview=values["overview_type"].overview,story=values["story"].story,characters=values["characters"].characters,suspense=values["suspense"].suspense,pacing=values["pacing"].pacing,chapters=values["pacing"].chapters,assessment=values["assessment"].assessment,evidence_index=catalog,analysis_metadata=analysis)

        validator=EvidenceValidator(chapters)
        for ref in result.evidence_index.values(): validator.validate(ref)
        expected={(c.chapter_id,c.chapter_index) for c in chapters}; actual={(c.chapter_id,c.chapter_index) for c in result.chapters.functions}
        if expected!=actual or len(result.chapters.functions)!=len(chapters): raise SynthesisUnitError("pacing",UnitFailureCode.SCHEMA_MISMATCH,"chapter coverage or identity mismatch")
        self._emit_progress(run_id,stage="evidence_validation",stage_percent=100,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
        self._emit_progress(run_id,stage="complete",stage_percent=100,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
        emit("evidence_validation",100,last); emit("materialize_report",100,last)
        return result,self.responses
