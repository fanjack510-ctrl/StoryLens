"""Formal read-only V2 result API. Creation remains owned by the existing run API."""
from __future__ import annotations
import os,re,shutil,subprocess,sys,tempfile,time
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
def missing()->HTTPException:return HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_RESULT_NOT_FOUND","message":"这本书还没有完整的全书分析结果。旧版本的分析结果不会被当作新版结果使用，需要重新分析一次。","details":{}})
@router.get("/{run_id}/v2")
def get_v2(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    result=r.load_result(run_id)
    if result is None: raise missing()
    return enrich_v2_payload(result,r.session)
@router.get("/{run_id}/v2/modules/{module}")
def get_v2_module(run_id:int,module:str,cursor:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    if module not in MODULES: raise HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_MODULE_NOT_FOUND","message":"没有这个分析模块。","details":{"module":module}})
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
    """Locate a Chromium-family browser already installed on the host."""
    candidates=[os.environ.get("STORYLENS_PDF_BROWSER")]
    if sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            str(os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
            str(os.path.expanduser("~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")),
        ]
    elif os.name == "nt":
        candidates += [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        candidates += [shutil.which(name) for name in (
            "google-chrome", "microsoft-edge", "chromium", "chromium-browser", "brave-browser"
        )]
    for c in candidates:
        if c and os.path.isfile(c): return c
    return None
_FOOTER_CSS="font-family:'Microsoft YaHei','PingFang SC',sans-serif;font-size:7.5px;color:#6f7d74;"
def _cleanup_pdf_workspace(path:str)->None:
    """Best-effort cleanup: a stale Chromium lock must never abort the HTTP response."""
    for delay in (0.0,0.08,0.2,0.5):
        if delay: time.sleep(delay)
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            pass
    shutil.rmtree(path,ignore_errors=True)

def _stop_pdf_browser(proc:subprocess.Popen[Any])->None:
    """Stop only the Chromium tree started for this export."""
    try:
        if proc.poll() is None and os.name == "nt":
            subprocess.run(
                ["taskkill","/PID",str(proc.pid),"/T","/F"],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,
            )
        elif proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
    except Exception:
        try: proc.kill()
        except Exception: pass
    try: proc.wait(timeout=5)
    except Exception: pass

def _print_via_devtools(
    browser:str,
    profile:str,
    url:str,
    title:str,
    timeout:float=90.0,
    *,
    report_label:str="全书分析报告",
)->bytes|None:
    """Print through DevTools, so the footer can carry a real page number.

    ``--print-to-pdf`` has no way to supply a header or footer template: it either omits them
    (``--no-pdf-header-footer``) or prints Chromium's default, which stamps the temporary
    ``file:///`` path of the source HTML onto every page — not something to hand a paying
    reader. ``Page.printToPDF`` takes a template, and ``<span class=pageNumber>`` is
    substituted by the browser, which is the only place the page count is actually known.

    Returns ``None`` on any failure rather than raising: the caller falls back to the CLI, and
    a report without page numbers is still a report.

    但那次回落必须留下一行日志。`websockets` 曾经根本没装（它不在 spec 的 hiddenimports 里，
    项目也没有 requirements），于是这个函数每次都在第一行 ImportError、返回 None，
    每一份付费导出的 PDF 都没有页码——而整整一个版本里没有任何人发现，
    因为回落是完全静默的。一条无声的降级路径，等于没有这条路径。
    """
    import asyncio,base64,json,logging,shutil
    _log=logging.getLogger(__name__)
    async def run()->bytes|None:
        import httpx,websockets
        port_file=os.path.join(profile,"DevToolsActivePort")
        proc=subprocess.Popen([browser,"--headless=new","--disable-gpu","--no-first-run",
            "--disable-extensions","--disable-background-mode","--remote-debugging-port=0",
            f"--user-data-dir={profile}",url],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            loop=asyncio.get_running_loop(); deadline=loop.time()+timeout; port=None; exited_at=None
            while loop.time()<deadline:
                if os.path.isfile(port_file):
                    head=open(port_file,encoding="utf-8").read().splitlines()
                    if head and head[0].strip().isdigit(): port=int(head[0].strip()); break
                # Edge can hand the profile to a child and let the launcher exit. Give that
                # child time to publish DevToolsActivePort instead of treating the hand-off as
                # a rendering failure (and then leaving its lockfile behind).
                if proc.poll() is not None:
                    exited_at=exited_at or loop.time()
                    if loop.time()-exited_at>8:
                        _log.warning("pdf_browser_exited_before_devtools exit_code=%s",proc.returncode)
                        return None
                await asyncio.sleep(0.15)
            if port is None:
                _log.warning("pdf_devtools_port_timeout")
                return None
            base=f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(timeout=10.0) as http:
                ws_url=None
                while loop.time()<deadline and ws_url is None:
                    try:
                        for t in (await http.get(f"{base}/json/list")).json():
                            if t.get("type")=="page" and t.get("webSocketDebuggerUrl"):
                                ws_url=t["webSocketDebuggerUrl"]; break
                    except Exception: pass
                    if ws_url is None: await asyncio.sleep(0.15)
                if ws_url is None: return None
            async with websockets.connect(ws_url,max_size=256*1024*1024) as ws:
                n=0
                async def call(method:str,params:dict[str,Any]|None=None)->dict[str,Any]:
                    nonlocal n; n+=1; mid=n
                    await ws.send(json.dumps({"id":mid,"method":method,"params":params or {}}))
                    while True:
                        msg=json.loads(await ws.recv())
                        if msg.get("id")==mid:
                            error=msg.get("error")
                            if error:
                                raise RuntimeError(f"CDP {method} failed: {error.get('message') or error}")
                            return msg.get("result") or {}
                await call("Page.enable")
                # The target exists before its document finishes; poll rather than race the load
                # event, which may already have fired by the time the websocket is attached.
                while loop.time()<deadline:
                    r=await call("Runtime.evaluate",{"expression":"document.readyState","returnByValue":True})
                    if (r.get("result") or {}).get("value")=="complete": break
                    await asyncio.sleep(0.1)
                safe=title.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                safe_label=report_label.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                res=await call("Page.printToPDF",{
                    "paperWidth":8.27,"paperHeight":11.69,
                    "marginTop":0.71,"marginBottom":0.63,"marginLeft":0.67,"marginRight":0.67,
                    "printBackground":True,"displayHeaderFooter":True,
                    "headerTemplate":"<span></span>",
                    "footerTemplate":(
                        f"<div style=\"{_FOOTER_CSS}width:100%;padding:0 17mm;display:flex;"
                        "justify-content:space-between;align-items:center;\">"
                        f"<span>{safe} · {safe_label}</span>"
                        "<span><span class=\"pageNumber\"></span> / <span class=\"totalPages\"></span></span>"
                        "</div>"),
                })
                data=res.get("data")
                try:
                    # No reply is required. The connection may close immediately, which is the
                    # desired outcome: release cdp-profile/lockfile before workspace cleanup.
                    await ws.send(json.dumps({"id":n+1,"method":"Browser.close","params":{}}))
                except Exception: pass
                return base64.b64decode(data) if data else None
        finally:
            _stop_pdf_browser(proc)
            _cleanup_pdf_workspace(profile)
    try:
        pdf=asyncio.run(run())
    except Exception:
        _log.warning("pdf_devtools_path_failed 回落到无页码的 --print-to-pdf",exc_info=True)
        return None
    if pdf is None:
        _log.warning("pdf_devtools_path_returned_nothing 回落到无页码的 --print-to-pdf")
    return pdf
def render_report_pdf(
    db:Session,
    html:str,
    *,
    report_label:str="全书分析报告",
)->Response:
    """把客户端渲染好的报告 HTML 打成 PDF。全书和单章共用这一条。

    客户端负责报告长什么样（它拥有版式与所有标签），这里只负责变成纸。同步执行：一份
    十二章的报告约 2 秒，调用方是一个带转圈的点击。

    Pro 门（advanced_export）：HTML 导出保持免费——它是可核对的那一份；成品 PDF 是付费档。
    """
    from app.services.entitlement import can_use_feature,commerce_config
    gate=can_use_feature(db,"advanced_export")
    if not gate.get("enabled"):
        commerce=commerce_config()
        raise HTTPException(status_code=403,detail={
            "error_code":"PDF_REQUIRES_VIP",
            "message":"PDF 导出是 StoryLens Pro 功能。可在爱发电购买授权，在设置中激活后使用；HTML 导出保持免费。",
            "details":{"feature_key":"advanced_export","reason":str(gate.get("reason") or ""),
                       "edition":str(gate.get("edition") or "free"),
                       "afdian_product_url":str(commerce.get("afdian_product_url") or ""),
                       "product_label":str(commerce.get("product_label") or "StoryLens Pro")}})
    browser=_find_pdf_browser()
    if browser is None:
        raise HTTPException(status_code=501,detail={"error_code":"PDF_BROWSER_NOT_FOUND","message":"未找到可用于生成 PDF 的 Chromium 浏览器（Edge、Chrome、Chromium 或 Brave）。","details":{}})
    td=tempfile.mkdtemp(prefix="storylens-pdf-")
    try:
        src=os.path.join(td,"report.html"); dst=os.path.join(td,"report.pdf")
        with open(src,"w",encoding="utf-8") as f: f.write(html)
        url="file:///"+src.replace("\\","/")
        m=re.search(r"<title>(.*?)</title>",html,re.S|re.I)
        pdf=_print_via_devtools(
            browser,
            os.path.join(td,"cdp-profile"),
            url,
            (m.group(1) if m else "").split("·")[0].strip(),
            report_label=report_label,
        )
        if pdf: return Response(content=pdf,media_type="application/pdf")
        last_err=b""
        for attempt,headless_flag in enumerate(("--headless=new","--headless"),start=1):
            cmd=[browser,headless_flag,"--disable-gpu","--no-first-run","--disable-extensions",
                 "--disable-background-mode",f"--user-data-dir={os.path.join(td,f'profile-{attempt}')}",
                 "--no-pdf-header-footer",
                 f"--print-to-pdf={dst}",url]
            return_code=None
            try:
                proc=subprocess.run(cmd,capture_output=True,timeout=120)
                return_code=proc.returncode
                last_err=proc.stderr or proc.stdout or f"Chromium exit code: {proc.returncode}".encode()
            except subprocess.TimeoutExpired:
                last_err=b"timeout"
            if return_code == 0:
                # Edge may return after handing work to a child. Wait briefly for the file.
                ready_deadline=time.monotonic()+8
                while time.monotonic()<ready_deadline and not (
                    os.path.isfile(dst) and os.path.getsize(dst)>0
                ):
                    time.sleep(0.1)
            if os.path.isfile(dst) and os.path.getsize(dst)>0: break
        if not (os.path.isfile(dst) and os.path.getsize(dst)>0):
            message=last_err.decode(errors="replace")[-500:].strip() or "Chromium 未生成 PDF。"
            raise HTTPException(status_code=500,detail={"error_code":"PDF_RENDER_FAILED","message":message,"details":{}})
        with open(dst,"rb") as f: pdf=f.read()
        return Response(content=pdf,media_type="application/pdf")
    finally:
        _cleanup_pdf_workspace(td)


@router.post("/{run_id}/v2/export-pdf")
def export_v2_pdf(run_id:int,req:_PdfRequest,db:Session=Depends(get_db))->Response:
    """全书报告转 PDF。run_id 只用于定位这次点击，渲染完全由传来的 HTML 决定。"""
    del run_id
    return render_report_pdf(db,req.html)

@router.get("/{run_id}/v2/progress")
def get_v2_progress(run_id:int,r:WholeBookV2Repository=Depends(repo))->dict[str,Any]:
    progress=r.load_progress(run_id)
    if progress is None: raise HTTPException(status_code=404,detail={"error_code":"WHOLE_BOOK_V2_PROGRESS_NOT_FOUND","message":"这次分析还没有进度可读。刚开始的分析要过一会儿才有第一条进度；如果分析已经结束，请刷新页面查看结果。","details":{}})
    return progress.model_dump(mode="json")
