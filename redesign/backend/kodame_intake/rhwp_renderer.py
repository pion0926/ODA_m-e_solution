"""Isolated, offline use of the exact rHWP assets shipped to the preview.

No report URL, user cookies or remote resources enter this renderer. Each
render gets a fresh browser context and is bounded by page/time limits.
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .rhwp_geometry import SVG_GEOMETRY_SCRIPT, validate_rendered_geometry

_RENDER_LOCK = threading.BoundedSemaphore(1)
ASSET_ROOT = Path(os.getenv("RHWP_ASSET_ROOT", "/app/rhwp"))

_BRIDGE = """() => {
  let seq = 0;
  window.reportRenderRequest = (method, params = {}) => new Promise((resolve, reject) => {
    const id = 'server-render-' + (++seq);
    const timer = setTimeout(() => {window.removeEventListener('message', listener); reject(Error(method + ' timed out'));}, 45000);
    function listener(event) {
      if (event.source !== window || event.data?.type !== 'rhwp-response' || event.data.id !== id) return;
      clearTimeout(timer); window.removeEventListener('message', listener);
      event.data.error ? reject(Error(event.data.error)) : resolve(event.data.result);
    }
    window.addEventListener('message', listener);
    window.postMessage({type:'rhwp-request',id,method,params}, location.origin);
  });
}"""


def analyze_rhwp(data: bytes, *, include_svgs: bool = False) -> dict:
    if not data or len(data) > 64 * 1024 * 1024:
        raise ValueError("rHWP 조판 파일 크기가 허용 범위를 벗어났습니다.")
    if not (ASSET_ROOT / "index.html").is_file():
        raise RuntimeError("rHWP 조판 자산이 배포되지 않았습니다.")
    if not _RENDER_LOCK.acquire(timeout=180):
        raise RuntimeError("rHWP 조판 대기 시간이 초과되었습니다. 잠시 후 재시도해 주세요.")
    started = time.monotonic()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as engine:
            browser = engine.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width":1280,"height":900}, locale="ko-KR")
                page.set_default_timeout(45000)

                def serve(route):
                    url = urlparse(route.request.url)
                    prefix = "/assets/rhwp/"
                    if url.hostname != "rhwp.local" or not url.path.startswith(prefix):
                        route.abort()
                        return
                    relative = unquote(url.path[len(prefix):]) or "index.html"
                    path = (ASSET_ROOT / relative).resolve()
                    if ASSET_ROOT.resolve() not in path.parents or not path.is_file():
                        route.fulfill(status=404, body="Not found")
                        return
                    mime = "application/wasm" if path.suffix == ".wasm" else mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    route.fulfill(status=200, body=path.read_bytes(), content_type=mime)

                page.route("**/*", serve)
                page.goto("http://rhwp.local/assets/rhwp/", wait_until="load")
                page.evaluate(_BRIDGE)
                page.evaluate("() => window.reportRenderRequest('ready')")
                page.evaluate("b64 => window.reportRenderRequest('loadFile', {data:Array.from(Uint8Array.from(atob(b64), c=>c.charCodeAt(0))),fileName:'report.hwpx',skipUnsavedGuard:true})", base64.b64encode(data).decode("ascii"))
                page.evaluate("() => document.fonts.ready.then(() => true)")
                total = page.evaluate("() => window.reportRenderRequest('pageCount')")
                if type(total) is not int or not 1 <= total <= 200:
                    raise RuntimeError(f"rHWP 페이지 수가 허용 범위를 벗어났습니다: {total}")
                rows = []
                for number in range(total):
                    if time.monotonic() - started > 180:
                        raise RuntimeError("rHWP 전체 조판 제한시간을 초과했습니다.")
                    row = page.evaluate("""async number => {
                      const raw = await window.reportRenderRequest('getPageSvg', {page:number});
                      const svg = typeof raw === 'string' ? raw : raw?.svg;
                      if (!svg) throw Error('Empty page SVG');
                      const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
                      const lines=[]; let y=null;
                      for (const node of doc.querySelectorAll('text')) {
                        const next=node.getAttribute('y');
                        if(y!==next || !lines.length) lines.push('');
                        lines[lines.length-1]+=node.textContent; y=next;
                      }
                      return {page_number:number+1,text:lines.join('\\n'),svg};
                    }""", number)
                    row['geometry'] = page.evaluate(SVG_GEOMETRY_SCRIPT, row['svg'])
                    if not include_svgs:
                        row.pop("svg", None)
                    rows.append(row)
                return {"renderer":"rhwp", "page_count":total, "page_texts":rows,
                        "source_sha256":hashlib.sha256(data).hexdigest(),
                        "elapsed_seconds":round(time.monotonic()-started, 3)}
            finally:
                browser.close()
    finally:
        _RENDER_LOCK.release()


def finalize_toc_with_rhwp(data: bytes, *, render=analyze_rhwp, max_passes: int = 4) -> tuple[bytes, dict]:
    """Compute TOC last; re-render the exact patched bytes until stable."""
    from .report_rhwp_verification import rhwp_page_map, rhwp_printed_page_map
    from .hwpx_layout.toc import patch_toc_page_numbers, validate_toc_page_numbers
    current = data
    history = []
    for attempt in range(max_passes):
        analysis = render(current)
        physical_page_map = rhwp_page_map(analysis)
        page_map = rhwp_printed_page_map(analysis, physical_page_map)
        visible = validate_toc_page_numbers(current, page_map)
        history.append({"pass":attempt+1,"page_count":analysis["page_count"],"page_map":page_map,
                        "physical_page_map":physical_page_map})
        if visible.get("ok"):
            geometry = validate_rendered_geometry(analysis)
            return current, {"ok":True,"source":"rhwp_final_render","page_map":page_map,
                             "physical_page_map":physical_page_map,"page_number_basis":"printed_footer",
                             "page_count":analysis["page_count"],"source_sha256":analysis["source_sha256"],
                             "passes":history,"visible_validation":visible,"geometry_validation":geometry,"analysis":analysis}
        current, changed = patch_toc_page_numbers(current, page_map)
        if not changed:
            raise RuntimeError("목차 표시값을 최종 rHWP 조판에 반영하지 못했습니다.")
    raise RuntimeError("목차 최종 조판 쪽수가 안정화되지 않았습니다. 잘못된 쪽수로 완료 처리하지 않았습니다.")
