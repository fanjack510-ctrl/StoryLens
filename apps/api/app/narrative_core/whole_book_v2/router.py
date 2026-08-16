"""Formal read-only V2 result API. Creation remains owned by the existing run API."""
from __future__ import annotations
import os,subprocess,tempfile
from typing import Any
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from .repository import WholeBookV2Repository
from .result_origin import enrich_v2_payload

router=APIRouter(prefix="/api/v1/whole-book-runs",tags=["whole-book-v2"])
MODULES={"overview","story","characters","suspense","pacing","chapters","assessment","type_profile"}
def repo(db:Session=Depends(get_db))->WholeBookV2Repository:return WholeBookV2Repository(db)
def missing()->HTTPException:return HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_RESULT_NOT_FOUND","message":"V2 result is not available; legacy results are not promoted to complete V2.","details":{}})
@router.get("/{run_id}/v2")
def get_v2(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    result=r.load_result(run_id)
    if result is None: raise missing()
    return enrich_v2_payload(result)
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
class _PdfRequest(BaseModel):
    html:str
def _find_pdf_browser()->str|None:
    """A Chromium the machine already has. Every supported Windows ships Edge; Chrome is a fallback."""
    candidates=[os.environ.get("STORYLENS_PDF_BROWSER"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
    for c in candidates:
        if c and os.path.isfile(c): return c
    return None
@router.post("/{run_id}/v2/export-pdf")
def export_v2_pdf(run_id:int,req:_PdfRequest,db:Session=Depends(get_db))->Response:
    """Print the client-rendered report HTML to a real PDF via a headless Chromium.

    The client builds the HTML (it owns the report's shape and label maps); this endpoint
    only turns it into paper. Kept synchronous: a 12-chapter report prints in ~2s and the
    caller is a click handler with a spinner.

    Pro-gated (advanced_export): the HTML export stays free — it is the audit surface —
    while the finished hand-off artifact is the paid tier, purchasable as an 爱发电 monthly
    card and activated in 设置."""
    from app.services.entitlement import can_use_feature,commerce_config
    gate=can_use_feature(db,"advanced_export")
    if not gate.get("enabled"):
        commerce=commerce_config()
        raise HTTPException(status_code=403,detail={
            "error_code":"PDF_REQUIRES_VIP",
            "message":"PDF 导出是 VIP（Pro）功能。可在爱发电购买月卡授权，在设置中激活后使用；HTML 导出保持免费。",
            "details":{"feature_key":"advanced_export","reason":str(gate.get("reason") or ""),
                       "edition":str(gate.get("edition") or "free"),
                       "afdian_product_url":str(commerce.get("afdian_product_url") or ""),
                       "product_label":str(commerce.get("product_label") or "StoryLens Pro")}})
    browser=_find_pdf_browser()
    if browser is None:
        raise HTTPException(status_code=501,detail={"error_code":"PDF_BROWSER_NOT_FOUND","message":"未找到可用于生成 PDF 的浏览器（Edge/Chrome）。","details":{}})
    with tempfile.TemporaryDirectory(prefix="storylens-pdf-") as td:
        src=os.path.join(td,"report.html"); dst=os.path.join(td,"report.pdf")
        with open(src,"w",encoding="utf-8") as f: f.write(req.html)
        url="file:///"+src.replace("\\","/")
        last_err=b""
        # --headless=new is current Chromium; plain --headless keeps older Edge builds working.
        for headless_flag in ("--headless=new","--headless"):
            cmd=[browser,headless_flag,"--disable-gpu","--no-first-run","--disable-extensions",
                 f"--user-data-dir={os.path.join(td,'profile')}","--no-pdf-header-footer",
                 f"--print-to-pdf={dst}",url]
            try:
                proc=subprocess.run(cmd,capture_output=True,timeout=120)
                last_err=proc.stderr or proc.stdout or b""
            except subprocess.TimeoutExpired:
                last_err=b"timeout"
            if os.path.isfile(dst) and os.path.getsize(dst)>0: break
        if not (os.path.isfile(dst) and os.path.getsize(dst)>0):
            raise HTTPException(status_code=500,detail={"error_code":"PDF_RENDER_FAILED","message":last_err.decode(errors="replace")[-500:],"details":{}})
        with open(dst,"rb") as f: pdf=f.read()
    return Response(content=pdf,media_type="application/pdf")
@router.get("/{run_id}/v2/progress")
def get_v2_progress(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    progress=r.load_progress(run_id)
    if progress is None: raise HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_PROGRESS_NOT_FOUND","message":"V2 progress is not available","details":{}})
    return progress.model_dump(mode="json")
