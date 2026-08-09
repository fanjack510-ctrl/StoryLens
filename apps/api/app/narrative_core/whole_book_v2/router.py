"""Formal read-only V2 result API. Creation remains owned by the existing run API."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from .repository import WholeBookV2Repository

router=APIRouter(prefix="/api/v1/whole-book-runs",tags=["whole-book-v2"])
MODULES={"overview","story","characters","suspense","pacing","chapters","assessment","type_profile"}
def repo(db:Session=Depends(get_db))->WholeBookV2Repository:return WholeBookV2Repository(db)
def missing()->HTTPException:return HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_RESULT_NOT_FOUND","message":"V2 result is not available; legacy results are not promoted to complete V2.","details":{}})
@router.get("/{run_id}/v2")
def get_v2(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    result=r.load_result(run_id)
    if result is None: raise missing()
    return result.model_dump(mode="json")
@router.get("/{run_id}/v2/modules/{module}")
def get_v2_module(run_id:int,module:str,cursor:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    if module not in MODULES: raise HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_MODULE_NOT_FOUND","message":"Unknown V2 module","details":{"module":module}})
    result=r.load_result(run_id)
    if result is None: raise missing()
    payload=getattr(result,module).model_dump(mode="json"); collection_key={"characters":"major_characters","suspense":"lifecycles","pacing":"points","chapters":"functions","assessment":"issues"}.get(module)
    next_cursor=None
    if collection_key:
        items=payload[collection_key]; payload[collection_key]=items[cursor:cursor+limit]; next_cursor=cursor+limit if cursor+limit<len(items) else None
    return {"schema_version":result.schema_version,"module":module,"availability":result.analysis_metadata.module_availability.get(module,"available"),"payload":payload,"next_cursor":next_cursor}
@router.get("/{run_id}/v2/progress")
def get_v2_progress(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    progress=r.load_progress(run_id)
    if progress is None: raise HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_PROGRESS_NOT_FOUND","message":"V2 progress is not available","details":{}})
    return progress.model_dump(mode="json")
