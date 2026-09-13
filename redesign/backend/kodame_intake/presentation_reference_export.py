"""15/30 page generation orchestration; profiles, prompts, photos and layout
are independently editable. Legacy exports remain readable through the API.
"""
import base64
import hashlib
import json
import re
from pathlib import Path

import httpx
from pypdf import PdfReader
from psycopg.types.json import Jsonb

from .db import connection, tenant_context
from .presentation_profiles import get_profile
from .presentation_reference_prompt import SYSTEM, batch_prompt, validate_batch
from .presentation_reference_renderer import build_reference_deck
from .presentation_photos import collect_project_photos
from .presentation_source import collect_presentation_source
from .presentation_quality import render_and_validate_presentation
from .settings import (OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_PRESENTATION_MODEL,
                       OPENROUTER_REFERER, DATA_DIR, PRESENTATION_MAX_GENERATION_ATTEMPTS)
from .usage import record_token_usage


def request_batch(profile, pages, source, photos, feedback):
    generated_pages = [p for p in pages if p['layout'] not in ('cover', 'toc')]
    automatic = {p['slide_number']: {'slide_number': p['slide_number'], 'title': p['title'],
                 'rows': [], 'blocks': [], 'photo_id': '', 'caption': '',
                 'speaker_notes': '저장된 사업 개요와 보고서 목차를 기준으로 구성함.',
                 'source_sections': p['source_sections'][:1]}
                 for p in pages if p['layout'] in ('cover', 'toc')}
    if not generated_pages:
        return [automatic[p['slide_number']] for p in pages]
    catalog = [{"id": key, "file_name": p["file_name"], "page": p["page"]} for key, p in photos.items()]
    content = [{"type": "text", "text": batch_prompt(profile, generated_pages, source, catalog, feedback)}]
    if any(p["layout"] == "photo" for p in generated_pages):
        for key, photo in photos.items():
            content.extend([{"type": "text", "text": key}, {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(photo["data"]).decode("ascii")}}])
    else:
        # Do not allow selecting a photograph that the model did not see.
        photos = {}
    with httpx.Client(timeout=httpx.Timeout(300, connect=20)) as client:
        response = client.post(f"{OPENROUTER_BASE_URL}/chat/completions", headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}", "HTTP-Referer": OPENROUTER_REFERER,
            "X-Title": "ODAME reference presentation",
        }, json={"model": OPENROUTER_PRESENTATION_MODEL, "messages": [
            {"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
            "response_format": {"type": "json_object"}, "temperature": .2,
            "reasoning": {"effort": "high", "exclude": True}, "max_completion_tokens": 14000})
        response.raise_for_status()
        result = response.json()
        record_token_usage(result, OPENROUTER_PRESENTATION_MODEL)
        message = result["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(v.get("text", "") for v in message)
        raw = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", message.strip()))
    generated = validate_batch(raw, generated_pages, source, photos)
    combined = {**automatic, **{p['slide_number']: p for p in generated}}
    return [combined[p['slide_number']] for p in pages]


def run_reference_export(export_id, project_id, slide_count=15):
    # Import lazily to keep the existing utility functions backward compatible.
    from .presentation_exporter import _update
    with tenant_context(project_id, system=project_id is None):
        try:
            profile = get_profile(slide_count)
            sample = Path('/app/samples/presentation_references/drive') / profile['reference_file']
            if not sample.is_file() or len(PdfReader(sample).pages) != profile['reference_page_count']:
                raise RuntimeError('등록된 샘플 PDF 또는 원본 장수가 일치하지 않습니다.')
            profile['reference_sha256'] = hashlib.sha256(sample.read_bytes()).hexdigest()
            _update(export_id, 5, "collecting", f"{slide_count}페이지 샘플 구성에 맞춰 저장 보고서와 사진 자료를 확인하는 중")
            context, source, flags = collect_presentation_source()
            photos = collect_project_photos(context.get("presentation_photo_document_ids", []))
            slides, history = [], []
            for start in range(0, slide_count, 3):
                pages = profile["pages"][start:start+3]
                feedback = ""
                for attempt in range(1, PRESENTATION_MAX_GENERATION_ATTEMPTS+1):
                    _update(export_id, 10+int(start/slide_count*70), "planning",
                            f"샘플 흐름에 맞춰 {start+1}~{start+len(pages)} / {slide_count}페이지 작성 중")
                    try:
                        used = {s["photo_id"] for s in slides if s.get("photo_id")}
                        available = {k: v for k, v in photos.items() if k not in used}
                        batch = request_batch(profile, pages, source, available, feedback)
                        selected = [s["photo_id"] for s in batch if s.get("photo_id")]
                        if len(selected) != len(set(selected)):
                            raise ValueError("같은 사진은 한 번만 사용해 주세요.")
                        if slide_count == 15:
                            for s in batch:
                                if s["slide_number"] == 1:
                                    s["photo_id"] = ""
                        # Check table/text geometry with the real renderer before
                        # committing this batch. Retry content, not font shrinking.
                        # Preserve sample styling and full-deck page labels.
                        build_reference_deck(profile, slides+batch, source, photos, partial=True)
                        slides.extend(batch)
                        history.append({"pages": [p["slide_number"] for p in pages], "attempt": attempt})
                        break
                    except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                        feedback = str(exc)[:800]
                        if attempt == PRESENTATION_MAX_GENERATION_ATTEMPTS:
                            raise RuntimeError(f"{start+1}페이지 묶음 검증 실패: {feedback}") from exc
            _update(export_id, 85, "rendering", f"전체 {slide_count}페이지를 원본 비율의 편집 가능한 PPTX로 변환하는 중")
            data = build_reference_deck(profile, slides, source, photos)
            plan = {"slide_count": slide_count, "slides": [dict(s, layout=p["layout"]) for p, s in zip(profile["pages"], slides)]}
            _update(export_id, 90, "visual_qa", f"{slide_count}페이지 렌더링과 본문 누락 검사 중")
            for qa_attempt in range(PRESENTATION_MAX_GENERATION_ATTEMPTS):
                try:
                    validation = render_and_validate_presentation(data, plan)
                    break
                except RuntimeError as exc:
                    match = re.search(r'(\d+)페이지', str(exc))
                    if not match or qa_attempt == PRESENTATION_MAX_GENERATION_ATTEMPTS-1:
                        raise
                    index = int(match.group(1))-1
                    replacement = request_batch(profile, [profile['pages'][index]], source, photos, str(exc))
                    slides[index] = replacement[0]
                    data = build_reference_deck(profile, slides, source, photos)
                    plan['slides'][index] = dict(slides[index], layout=profile['pages'][index]['layout'])
            validation.update({"slide_count": slide_count, "profile_id": profile["id"],
                               "profile_version": profile["version"], "reference_file": profile["reference_file"],
                               "reference_page_count": profile["reference_page_count"],
                               "reference_sha256": profile['reference_sha256'],
                               "source_page_mapping": [p["source_pages"] for p in profile["pages"]],
                               "photos_used": len({s['photo_id'] for s in slides if s.get('photo_id')}),
                               "photo_candidates": len(photos), "attempts": history,
                               "source_section_coverage": len({k for s in slides for k in s["source_sections"]}),
                               "local_sensitive_flags": flags})
            directory = DATA_DIR / "presentation_exports"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{export_id}.pptx"
            path.write_bytes(data)
            # Retain exact pre-render content for reproducibility and QA.
            (directory / f"{export_id}.json").write_text(json.dumps({"profile": profile, "slides": slides, "source_summary": source["summary"]}, ensure_ascii=False, indent=2), encoding="utf-8")
            name = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", context["project"]["title"])[:70]
            with connection() as conn, conn.transaction():
                conn.execute("""UPDATE presentation_exports SET status='completed',progress=100,stage='completed',
                    message=%s,file_name=%s,output_path=%s,validation=%s,error_message=NULL,completed_at=now(),updated_at=now()
                    WHERE id=%s""", (f"{slide_count}페이지 샘플 기반 발표자료 생성 완료", f"{name}_발표자료_{slide_count}장.pptx", str(path), Jsonb(validation), export_id))
        except Exception as exc:
            with connection() as conn, conn.transaction():
                conn.execute("""UPDATE presentation_exports SET status='failed',stage='failed',message='발표자료 생성 실패',
                    error_message=%s,completed_at=now(),updated_at=now() WHERE id=%s""", (str(exc)[:1800], export_id))
