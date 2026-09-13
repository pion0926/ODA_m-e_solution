"""Read-only preview transport. Auth/menu/RLS use the existing request middleware."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from .db import connection
from .hwpx_adapters.registry import SPEC_BY_PART
from .report_section_preview import build_section_preview
from backend.oda_me.hwpx.adapters.contracts import AdapterContractError

router = APIRouter(prefix="/api/v2/report/sections", tags=["report-section-preview"])


class SectionPreviewRequest(BaseModel):
    content: str = Field(max_length=200000)


@router.post("/{part_id}/preview")
def preview_section(part_id: str, payload: SectionPreviewRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    if part_id not in SPEC_BY_PART:
        raise HTTPException(404, "보고서 섹션을 찾을 수 없습니다.")
    with connection() as conn:
        row = conn.execute("SELECT part_id FROM report_sections WHERE part_id=%s", (part_id,)).fetchone()
    if not row:
        raise HTTPException(404, "현재 프로젝트의 섹션을 찾을 수 없습니다.")
    try:
        return build_section_preview(part_id, payload.content)
    except (ValueError, AdapterContractError) as exc:
        raise HTTPException(422, str(exc)) from exc
