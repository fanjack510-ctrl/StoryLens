"""V2 materialization in existing Narrative Asset JSON; no migration required."""
from __future__ import annotations
import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import NarrativeAssetVersion, WholeBookCheckpoint, WholeBookRun
from app.narrative_core.services.asset_service import NarrativeAssetService
from .contracts import ProgressV2, WholeBookAnalysisV2

ASSET_TYPE="whole_book_analysis_v2"
class WholeBookV2Repository:
    def __init__(self,session:Session): self.session=session
    def save_result(self,result:WholeBookAnalysisV2)->int:
        run_id=result.analysis_metadata.run_id
        existing=self.session.scalars(select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id==run_id,NarrativeAssetVersion.asset_type==ASSET_TYPE).order_by(NarrativeAssetVersion.id.desc())).first()
        payload=result.model_dump_json()
        if existing is not None:
            if existing.attributes_json==payload: return int(existing.id)
            raise ValueError("successful V2 result already materialized for run")
        mutation=NarrativeAssetService(self.session).create_candidate_asset(result.book_metadata.book_id,asset_type=ASSET_TYPE,title=f"Whole-Book V2: {result.book_metadata.title}",summary=result.overview.one_sentence_story,run_id=run_id,book_snapshot_id=result.book_metadata.snapshot_id,stable_label=f"whole-book-v2:{run_id}",attributes_json=payload,source_fingerprint=result.book_metadata.revision_hash,origin_type="model")
        self.session.flush(); return int(mutation.version.id)
    def load_result(self,run_id:int)->WholeBookAnalysisV2|None:
        row=self.session.scalars(select(NarrativeAssetVersion).where(NarrativeAssetVersion.run_id==run_id,NarrativeAssetVersion.asset_type==ASSET_TYPE).order_by(NarrativeAssetVersion.id.desc())).first()
        return None if row is None else WholeBookAnalysisV2.model_validate_json(row.attributes_json)
    def save_progress(self,run_id:int,progress:ProgressV2)->None:
        row=self.session.scalars(select(WholeBookCheckpoint).where(WholeBookCheckpoint.run_id==run_id,WholeBookCheckpoint.stage_code=="v2_progress",WholeBookCheckpoint.checkpoint_key=="latest")).first(); payload=progress.model_dump_json()
        if row is None:
            row=WholeBookCheckpoint(run_id=run_id,stage_code="v2_progress",checkpoint_key="latest",sequence_no=1,completed_unit_count=progress.provider_calls_completed,payload_hash="",checkpoint_payload_json=payload); self.session.add(row)
        else:
            row.sequence_no+=1; row.completed_unit_count=progress.provider_calls_completed; row.checkpoint_payload_json=payload
        self.session.flush()
    def load_progress(self,run_id:int)->ProgressV2|None:
        row=self.session.scalars(select(WholeBookCheckpoint).where(WholeBookCheckpoint.run_id==run_id,WholeBookCheckpoint.stage_code=="v2_progress",WholeBookCheckpoint.checkpoint_key=="latest")).first()
        return None if row is None else ProgressV2.model_validate_json(row.checkpoint_payload_json)

def pinned_provider(session:Session,run_id:int)->tuple[str,str]:
    run=session.get(WholeBookRun,run_id)
    if run is None: raise LookupError("whole-book run not found")
    if not run.provider_name or not run.model_name: raise ValueError("run provider/model pin required")
    return str(run.provider_name),str(run.model_name)
