"""Reliable, unit-scoped real-provider synthesis for Whole-Book V2.

Hierarchical flow:
  chapters → window plan → Provider window extraction → intermediates → bounded synthesis
Final synthesis units never receive raw full-book chapter text.

CHG-084: Formal production forbids deterministic semantic scaffold as novel analysis.
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
    AssetLedger, ProviderBudget, WindowExtractionAsset, assert_context_safe,
    build_cost_plan, build_token_plan, build_topic_intermediates,
    contains_raw_chapter_text, extract_window_asset, infer_genre_profile,
    materialize_from_intermediates, plan_windows,
    synthesis_payload_from_intermediates,
)
from .runtime import ProviderUnitLedger
from .window_extraction import (
    ORIGIN_REAL,
    ProviderWindowExtractionPayload,
    build_window_evidence_catalog,
    contains_scaffold_semantics,
    is_reusable_real_provider_intermediate,
    materialize_window_asset_from_provider,
    parse_provider_window_payload,
)

ProgressCallback = Callable[[str, float, int], None]

class UnitFailureCode(StrEnum):
    TRUNCATED_JSON="TRUNCATED_JSON"; INVALID_JSON="INVALID_JSON"
    SCHEMA_MISMATCH="SCHEMA_MISMATCH"; MISSING_REQUIRED_FIELD="MISSING_REQUIRED_FIELD"
    INVALID_ENUM="INVALID_ENUM"; EVIDENCE_REFERENCE_INVALID="EVIDENCE_REFERENCE_INVALID"
    CONTEXT_UNSAFE="CONTEXT_UNSAFE"; SCAFFOLD_FORBIDDEN="SCAFFOLD_FORBIDDEN"

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

UNIT_REQUIRED_HINTS:dict[str,str]={
    "overview_type": (
        "Required top-level fields: type_profile AND overview. "
        "Do not return type_profile alone. overview MUST include all OverviewResult fields "
        "(one_sentence_story, full_summary, protagonist, core_goal, core_conflict, evidence, ...)."
    ),
    "story": (
        "Required top-level field: story. "
        "story MUST include structure_stages, storylines, causal_chain, and chronology. "
        "Do not omit storylines, causal_chain, or chronology."
    ),
    "characters": (
        "Required top-level field: characters. "
        "characters MUST include protagonist, major_characters, and relationships."
    ),
    "suspense": (
        "Required top-level field: suspense. "
        "suspense MUST include lifecycles with typed events."
    ),
    "pacing": (
        "Required top-level fields: pacing AND chapters. "
        "Must include pacing (points/event_markers/pacing_regions) AND chapters.functions covering every chapter."
    ),
    "assessment": (
        "Required top-level field: assessment. "
        "assessment MUST include overall_summary, dimensions, strengths, issues, issue_map, revision_priorities, preserve_list."
    ),
}

# Explicit top-level keys that must appear in both base + repair prompts (CHG-085).
UNIT_REQUIRED_TOP_LEVEL:dict[str,tuple[str,...]]={
    "overview_type":("type_profile","overview"),
    "story":("story",),
    "characters":("characters",),
    "suspense":("suspense",),
    "pacing":("pacing","chapters"),
    "assessment":("assessment",),
}

# Failure / run.current_stage_code mapping (CHG-085). Progress UI may still use V2_STAGES labels.
UNIT_FAILURE_STAGES:dict[str,str]={
    "overview_type":"overview_synthesis",
    "story":"story_synthesis",
    "characters":"characters_synthesis",
    "suspense":"suspense_synthesis",
    "pacing":"pacing_synthesis",
    "assessment":"assessment_synthesis",
}

UNIT_PROGRESS_STAGES:dict[str,str]={
    "overview_type":"generate_overview",
    "story":"consolidate_story",
    "characters":"consolidate_characters",
    "suspense":"merge_suspense",
    "pacing":"compute_pacing",
    "assessment":"generate_assessment",
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

def required_top_level_fields(schema:type[BaseModel],key:str)->tuple[str,...]:
    """Align prompt requirements with Pydantic JSON schema required properties."""
    declared=UNIT_REQUIRED_TOP_LEVEL.get(key)
    js=schema.model_json_schema()
    schema_required=tuple(js.get("required") or ())
    if declared is None:
        return schema_required
    if set(declared)!=set(schema_required):
        # Prefer schema as source of truth; keep declared order when equal.
        return schema_required or declared
    return declared

def _format_required_fields(fields:tuple[str,...]|list[str])->str:
    return "\n".join(f"- {name}" for name in fields)

def build_synthesis_unit_prompt(
    key:str,
    schema:type[BaseModel],
    synthesis_payload:dict[str,Any],
)->str:
    fields=required_top_level_fields(schema,key)
    hint=UNIT_REQUIRED_HINTS.get(key,"")
    return (
        f"Return only a complete JSON object for synthesis unit {key}. "
        "No Markdown. No commentary. Use the exact schema. Be concrete; do not use placeholders.\n"
        f"{hint}\n"
        "Required top-level fields (ALL mandatory — never omit any):\n"
        f"{_format_required_fields(fields)}\n"
        "Evidence arrays may only use supplied evidence_id values. "
        "INPUT is hierarchical intermediate assets only — not raw novel text.\n"
        f"SCHEMA:\n{json.dumps(schema.model_json_schema(),ensure_ascii=False)}\n"
        f"HIERARCHICAL_INTERMEDIATES:\n{json.dumps(synthesis_payload,ensure_ascii=False)}"
    )

def build_synthesis_repair_prompt(
    key:str,
    schema:type[BaseModel],
    *,
    error:SynthesisUnitError,
    invalid_output:str,
)->str:
    fields=required_top_level_fields(schema,key)
    hint=UNIT_REQUIRED_HINTS.get(key,"")
    return (
        f"Repair ONLY synthesis unit {key}. Return the COMPLETE corrected JSON object matching SCHEMA.\n"
        "Do NOT return only the missing fields. Do NOT return a partial patch. Do NOT use Markdown.\n"
        f"{hint}\n"
        "Required top-level fields (ALL mandatory):\n"
        f"{_format_required_fields(fields)}\n"
        f"ERROR_CODE={error.code}\n"
        f"VALIDATION_ERROR:\n{str(error)[:2000]}\n"
        f"SCHEMA:\n{json.dumps(schema.model_json_schema(),ensure_ascii=False)}\n"
        f"INVALID_UNIT_OUTPUT:\n{invalid_output}"
    )

def _evidence_refs(value:Any)->set[str]:
    out:set[str]=set()
    if isinstance(value,dict):
        for key,item in value.items():
            if key=="evidence" and isinstance(item,list): out.update(x for x in item if isinstance(x,str))
            else: out.update(_evidence_refs(item))
    elif isinstance(value,list):
        for item in value: out.update(_evidence_refs(item))
    return out

def _uses_deterministic_extraction(gateway:Any)->bool:
    """Formal production defaults to Provider extraction when generate() exists."""
    if not hasattr(gateway, "generate"):
        return True
    return bool(getattr(gateway, "deterministic_extraction", False))

class GatewayWholeBookV2Analyzer:
    ENGINE_VERSION="2.1.0"
    def __init__(self,gateway:Any,*,provider_name:str,model_name:str,ledger:ProviderUnitLedger|None=None,repository:Any|None=None,max_output_tokens:int=4000,budget:ProviderBudget|None=None,asset_ledger:AssetLedger|None=None,db_session:Any|None=None,force_full_reanalysis:bool=False):
        self.gateway=gateway; self.provider_name=provider_name; self.model_name=model_name
        self.ledger=ledger or ProviderUnitLedger(); self.repository=repository
        self.max_output_tokens=max_output_tokens; self.stats=UnitStats(); self.responses:list[ModelResponse]=[]
        self.budget=budget or ProviderBudget(provider=provider_name,model=model_name,expected_output=max_output_tokens)
        self.asset_ledger=asset_ledger or AssetLedger()
        self.last_token_plan=None; self.last_cost_plan=None; self.last_windows=None
        self.last_synthesis_payload=None; self.progress_events:list[ProgressV2]=[]
        self.db_session=db_session
        # force_full_reanalysis only governs cross-run intermediate copy at create time.
        # Same-run resume MUST always reuse THIS run's successful checkpoints (CHG-085).
        self.force_full_reanalysis=bool(force_full_reanalysis)
        self._last_overall=0.0
        self._active_run_id=0
        self.last_failure_stage:str|None=None

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
                if key.startswith("window:") and not is_reusable_real_provider_intermediate(cached):
                    return None
                self.stats.reused_units+=1
                return cached
        cached=self.asset_ledger.load(key)
        if cached is not None and key.startswith("window:") and not is_reusable_real_provider_intermediate(cached):
            return None
        return cached

    def _restore_progress_baseline(self,run_id:int)->None:
        """Resume provider-call / overall percent from persisted progress (CHG-085)."""
        if self.repository is None or not hasattr(self.repository,"load_progress"):
            return
        prev=self.repository.load_progress(int(run_id))
        if prev is None:
            return
        self.stats.provider_calls=max(self.stats.provider_calls,int(prev.provider_calls_completed or 0))
        self._last_overall=max(self._last_overall,float(prev.overall_percent or 0.0))

    def _save_asset(self,run_id:int,key:str,value:Any)->None:
        self.asset_ledger.save(key,value)
        if self.repository and hasattr(self.repository,"save_intermediate"):
            self.repository.save_intermediate(run_id,key,value)

    def _emit_progress(self,run_id:int,*,stage:str,stage_percent:float,current_window:int,total_windows:int,current_chapter:int,total_chapters:int,estimated_calls:int,elapsed:int=1)->ProgressV2:
        idx=V2_STAGES.index(stage) if stage in V2_STAGES else 0
        snap=progress_snapshot(stage_index=idx,stage_percent=stage_percent,current_window=current_window,total_windows=total_windows,current_chapter=current_chapter,total_chapters=total_chapters,provider_calls_completed=self.stats.provider_calls,provider_calls_estimated=estimated_calls,provider=self.provider_name,model=self.model_name,elapsed=elapsed,last_action=V2_STAGE_LABELS.get(stage,stage),current_action=V2_STAGE_LABELS.get(stage,stage),estimated_cost=(self.last_cost_plan.estimated_cost_low if self.last_cost_plan else 0),actual_cost=0,repairs=self.stats.repair_calls)
        if snap.overall_percent < self._last_overall:
            snap=snap.model_copy(update={"overall_percent": self._last_overall})
        self._last_overall=float(snap.overall_percent)
        self.progress_events.append(snap)
        if self.repository: self.repository.save_progress(run_id,snap)
        return snap

    async def _call(self,key:str,schema:type[BaseModel]|None,prompt:str,*,repair:bool=False,window_id:str|None=None)->ModelResponse:
        est=max(1,len(prompt)//2)+self.max_output_tokens
        if est>(self.budget.context_limit-self.budget.safety_margin):
            raise SynthesisUnitError(key,UnitFailureCode.CONTEXT_UNSAFE,f"estimated tokens {est} exceed safe context")
        req_schema=schema.model_json_schema() if schema is not None else None
        response=await self.gateway.generate(self.provider_name,ModelRequest(model=self.model_name,messages=[{"role":"user","content":prompt}],temperature=0.1,max_output_tokens=self.max_output_tokens,response_schema=req_schema,response_format_mode="json_object",enable_thinking=False))
        self.stats.provider_calls+=1; self.stats.repair_calls+=int(repair); self.responses.append(response)
        if self.db_session is not None and self._active_run_id:
            from .usage_ledger import record_provider_call
            record_provider_call(
                self.db_session,
                whole_book_run_id=int(self._active_run_id),
                unit_key=key,
                provider=self.provider_name,
                model=self.model_name,
                response=response,
                repair=repair,
                window_id=window_id,
            )
        return response

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
        self.last_failure_stage=UNIT_FAILURE_STAGES.get(key,key)
        base=build_synthesis_unit_prompt(key,schema,synthesis_payload)
        response=await self._call(key,schema,base)
        try:
            value=self._validate(key,schema,response,catalog)
            self._validate_business(key,value,chapter_count,response)
        except SynthesisUnitError as first:
            repair=build_synthesis_repair_prompt(
                key,schema,error=first,invalid_output=response.text,
            )
            repaired=await self._call(key,schema,repair,repair=True)
            try:
                value=self._validate(key,schema,repaired,catalog)
                self._validate_business(key,value,chapter_count,repaired)
            except SynthesisUnitError:
                self.last_failure_stage=UNIT_FAILURE_STAGES.get(key,key)
                raise
        self._save(run_id,key,value); return value

    async def _extract_window_provider(self,*,run_id:int,window:Any,metas:list[Any])->WindowExtractionAsset:
        catalog=build_window_evidence_catalog(window,metas)
        chapter_payload=[{"chapter_id":c.chapter_id,"chapter_index":c.chapter_index,"title":c.title,"text":c.text} for c in metas if c.chapter_id in set(window.chapter_ids)]
        evidence_catalog=[{"evidence_id":e.evidence_id,"chapter_id":e.chapter_id,"chapter_index":e.chapter_index,"chapter_title":e.chapter_title,"offset":e.start_offset,"excerpt":e.quote_or_excerpt} for e in catalog]
        schema=ProviderWindowExtractionPayload
        prompt=(
            "Extract SHORT structured window primitives as JSON only. No essay. No commentary. "
            "Use short fields; avoid duplication. Cite evidence ONLY via evidence_ids from EVIDENCE_CATALOG. "
            "Do NOT invent chapter_id/offset/excerpt. Do NOT use template placeholders "
            "(no 悬念@ / 阶段起点 / 围绕目标、阻力与选择形成完整阶段).\n"
            f"SCHEMA:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
            f"WINDOW:\n{json.dumps(window.model_dump(mode='json'), ensure_ascii=False)}\n"
            f"EVIDENCE_CATALOG:\n{json.dumps(evidence_catalog, ensure_ascii=False)}\n"
            f"CHAPTERS:\n{json.dumps(chapter_payload, ensure_ascii=False)}"
        )
        key=f"window:{window.window_id}"
        response=await self._call(key,schema,prompt,window_id=window.window_id)
        recovered=recover_json_object(response.text)
        if recovered is None:
            raise SynthesisUnitError(key,UnitFailureCode.TRUNCATED_JSON if response.finish_reason in {"length","max_tokens"} else UnitFailureCode.INVALID_JSON,"window extraction JSON invalid",response)
        try:
            payload=parse_provider_window_payload(recovered)
            asset=materialize_window_asset_from_provider(
                window=window,catalog=catalog,payload=payload,
                provider=self.provider_name,model=self.model_name,origin=ORIGIN_REAL,
                provider_request_id=getattr(response,"request_id",None) or getattr(response,"provider_request_id",None),
                input_tokens=response.input_tokens,output_tokens=response.output_tokens,
            )
        except Exception as exc:
            repair=(
                f"Repair window extraction JSON only. Return complete object matching schema. "
                f"Cite evidence_ids from catalog only. ERROR={str(exc)[:1500]}\n"
                f"SCHEMA:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
                f"EVIDENCE_CATALOG:\n{json.dumps(evidence_catalog, ensure_ascii=False)}\n"
                f"INVALID_OUTPUT:\n{response.text}"
            )
            repaired=await self._call(key,schema,repair,repair=True,window_id=window.window_id)
            recovered2=recover_json_object(repaired.text) or {}
            payload=parse_provider_window_payload(recovered2)
            asset=materialize_window_asset_from_provider(
                window=window,catalog=catalog,payload=payload,
                provider=self.provider_name,model=self.model_name,origin=ORIGIN_REAL,
                provider_request_id=getattr(repaired,"request_id",None) or getattr(repaired,"provider_request_id",None),
                input_tokens=repaired.input_tokens,output_tokens=repaired.output_tokens,
            )
        self.stats.window_calls+=1
        return asset

    async def analyze(self,*,run_id:int,book_id:int,title:str,chapters:list[SourceChapter],progress:ProgressCallback|None=None)->tuple[WholeBookAnalysisV2,list[ModelResponse]]:
        if not chapters: raise ValueError("chapters required")
        self._active_run_id=int(run_id)
        self._restore_progress_baseline(int(run_id))
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

        extractions:list[WindowExtractionAsset]=[]
        use_scaffold=_uses_deterministic_extraction(self.gateway)
        disallow_local=bool(getattr(self.gateway,"disallow_local_merge",False))
        for i,window in enumerate(windows,1):
            key=f"window:{window.window_id}"
            self.last_failure_stage="window_extraction"
            cached=self._load_asset(run_id,key)
            if cached is not None:
                asset=cached if isinstance(cached, WindowExtractionAsset) else WindowExtractionAsset.model_validate(cached)
                if not is_reusable_real_provider_intermediate(asset) and disallow_local and not use_scaffold:
                    cached=None
                    asset=None  # type: ignore[assignment]
            if cached is not None:
                asset=cached if isinstance(cached, WindowExtractionAsset) else WindowExtractionAsset.model_validate(cached)
            else:
                if use_scaffold:
                    if disallow_local:
                        raise SynthesisUnitError(key,UnitFailureCode.SCAFFOLD_FORBIDDEN,"formal production forbids deterministic_extraction scaffold")
                    asset=extract_window_asset(window,metas)
                    self.stats.window_calls+=1
                else:
                    asset=await self._extract_window_provider(run_id=run_id,window=window,metas=metas)
                self._save_asset(run_id,key,asset)
            if disallow_local and not is_reusable_real_provider_intermediate(asset) and not use_scaffold:
                raise SynthesisUnitError(key,UnitFailureCode.SCAFFOLD_FORBIDDEN,"non-real_provider window intermediate rejected")
            extractions.append(asset)
            self._emit_progress(run_id,stage="extract_windows",stage_percent=(i/len(windows))*100,current_window=i,total_windows=len(windows),current_chapter=window.end_chapter_index,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
            emit("extract_windows",(i/len(windows))*100,window.end_chapter_index)

        self.last_failure_stage="story_consolidation"
        intermediates=build_topic_intermediates(extractions)
        for topic in intermediates:
            tkey=f"topic:{topic}"
            self.last_failure_stage={
                "story_intermediate":"story_consolidation",
                "character_intermediate":"character_consolidation",
                "relationship_intermediate":"relationship_consolidation",
                "protagonist_arc_intermediate":"protagonist_arc_consolidation",
                "suspense_intermediate":"suspense_consolidation",
                "pacing_intermediate":"pacing_consolidation",
                "chapter_function_intermediate":"chapter_function_consolidation",
            }.get(topic,"story_consolidation")
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
        if not force_local:
            for key,schema in UNIT_SCHEMAS.items():
                stage=UNIT_PROGRESS_STAGES.get(key,"generate_overview")
                self.last_failure_stage=UNIT_FAILURE_STAGES.get(key,key)
                self._emit_progress(run_id,stage=stage,stage_percent=10,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
                emit(key,10,last)
                try:
                    values[key]=await self._unit(run_id,key,schema,synthesis_payload,catalog,len(chapters))
                except Exception:
                    if disallow_local:
                        raise
                    force_local=True
                    break
                self._emit_progress(run_id,stage=stage,stage_percent=100,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
                emit(key,100,last)

        metadata=BookMetadata(book_id=book_id,snapshot_id=chapters[0].snapshot_id,revision_hash=chapters[0].revision_hash,title=title,chapter_count=len(chapters),character_count=sum(len(c.text) for c in chapters))
        used_local=bool(force_local or len(values)<len(UNIT_SCHEMAS))
        if used_local:
            if disallow_local:
                raise SynthesisUnitError("synthesis",UnitFailureCode.SCHEMA_MISMATCH,"local merge forbidden for real acceptance")
            genre=infer_genre_profile(extractions)
            modules=materialize_from_intermediates(chapters=metas,intermediates=intermediates,evidence_index=catalog,genre_profile=genre)
            analysis=AnalysisMetadata(
                run_id=run_id,engine_version=self.ENGINE_VERSION,provider_name=self.provider_name,model_name=self.model_name,
                module_availability={k:Availability.AVAILABLE for k in ["overview","story","characters","suspense","pacing","chapters","assessment"]},
                provider_calls_completed=self.stats.provider_calls,real_provider_calls=0,result_origin="deterministic_local_merge",
                pipeline_version=f"whole_book_v2_hierarchical/{self.ENGINE_VERSION}",source_revision=chapters[0].revision_hash,
            )
            result=WholeBookAnalysisV2(book_metadata=metadata,type_profile=modules["type_profile"],overview=modules["overview"],story=modules["story"],characters=modules["characters"],suspense=modules["suspense"],pacing=modules["pacing"],chapters=modules["chapters"],assessment=modules["assessment"],evidence_index=catalog,analysis_metadata=analysis)
        else:
            analysis=AnalysisMetadata(
                run_id=run_id,engine_version=self.ENGINE_VERSION,provider_name=self.provider_name,model_name=self.model_name,
                module_availability={k:Availability.AVAILABLE for k in ["overview","story","characters","suspense","pacing","chapters","assessment"]},
                provider_calls_completed=self.stats.provider_calls,real_provider_calls=self.stats.provider_calls,result_origin="real_provider",
                pipeline_version=f"whole_book_v2_hierarchical/{self.ENGINE_VERSION}",source_revision=chapters[0].revision_hash,
            )
            result=WholeBookAnalysisV2(book_metadata=metadata,type_profile=values["overview_type"].type_profile,overview=values["overview_type"].overview,story=values["story"].story,characters=values["characters"].characters,suspense=values["suspense"].suspense,pacing=values["pacing"].pacing,chapters=values["pacing"].chapters,assessment=values["assessment"].assessment,evidence_index=catalog,analysis_metadata=analysis)

        if disallow_local:
            if result.analysis_metadata.result_origin != "real_provider":
                raise SynthesisUnitError(
                    "synthesis",
                    UnitFailureCode.SCAFFOLD_FORBIDDEN,
                    "formal completed result requires real_provider without scaffold semantics",
                )
            non_real_windows = [
                a for a in extractions if not is_reusable_real_provider_intermediate(a)
            ]
            if non_real_windows:
                raise SynthesisUnitError(
                    "synthesis",
                    UnitFailureCode.SCAFFOLD_FORBIDDEN,
                    "formal completed result requires real_provider window intermediates",
                )

        validator=EvidenceValidator(chapters)
        for ref in result.evidence_index.values(): validator.validate(ref)
        expected={(c.chapter_id,c.chapter_index) for c in chapters}; actual={(c.chapter_id,c.chapter_index) for c in result.chapters.functions}
        if expected!=actual or len(result.chapters.functions)!=len(chapters): raise SynthesisUnitError("pacing",UnitFailureCode.SCHEMA_MISMATCH,"chapter coverage or identity mismatch")
        self._emit_progress(run_id,stage="evidence_validation",stage_percent=100,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
        self._emit_progress(run_id,stage="complete",stage_percent=100,current_window=len(windows),total_windows=len(windows),current_chapter=last,total_chapters=len(chapters),estimated_calls=token_plan.estimated_total_calls)
        emit("evidence_validation",100,last); emit("materialize_report",100,last)
        return result,self.responses
