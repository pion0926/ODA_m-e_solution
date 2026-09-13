from __future__ import annotations

import argparse
import hashlib
import re
import uuid
from pathlib import Path

from psycopg.types.json import Jsonb
from pypdf import PdfReader

from report_prompts import EDITOR_REPORT_PARTS

from .db import connection, open_pool, pool


SAMPLE_DIR = Path("/app/samples")

# These terms rank pages inside completed reports. They are deliberately about
# section form and reasoning, not about the current project's subject matter.
SECTION_GUIDANCE: dict[str, dict] = {
    "cover": {"keywords": ["종료평가 결과보고서", "평가책임자", "평가수행기관"], "structure": "사업명, 보고서명, 기준연월, 평가책임자와 수행기관만 간결하게 제시한다."},
    "toc": {"keywords": ["목 차", "평가결과 요약", "기준별 평가결과", "환류과제"], "structure": "공식 장·절 체계를 유지하고 작성 안내문은 제외한다."},
    "notice": {"keywords": ["평가보고서 관련 공지", "책임 평가자", "평가 품질"], "structure": "평가 책임, 독립성, 사실확인과 품질관리 범위를 공식 문체로 명시한다."},
    "grade": {"keywords": ["평가 등급 결과표", "종합 점수", "산정 이유", "평가 기준"], "structure": "평가질문 행에만 핵심 근거를 쓰고 평점 행의 산정 이유는 비운 뒤 기준별 평균과 종합등급을 검산한다."},
    "summary-ko": {"keywords": ["국문 요약", "평가결과 요약", "성과 달성도", "기준별 평가결과", "결론"], "structure": "(1) 대상사업개요-(2) 평가개요-(3) 성과달성도-(4) 기준별 평가결과-(5) 결론의 다섯 상위 항목을 고정하고, 5,800~9,000자와 HWPX 4쪽 이상의 밀도를 확보하며 각 항목을 ㅇ 요지와 - 세부 판단으로 구성한다. 괄호형 세부 요약은 큰 논거 구분이 필요한 경우에만 선택적으로 사용한다."},
    "project-background": {"keywords": ["사업 추진배경", "추진경위", "개발수요", "국가 정책", "사업요청서"], "structure": "핵심 개발문제에서 시작해 문제의 규모와 원인, 정책 대응, 대상지역 수요, ODA 정합성, 사업 형성 논리를 연결한다. 각 관점은 `(구체적 소제목) 본문`으로 작성하며 HWPX에서 `ㅇ (소제목)` 다음 줄 본문으로 렌더링한다."},
    "project-overview": {"keywords": ["사업개요", "사업기간", "사업예산", "수혜자", "수행기관"], "structure": "확정 사업정보와 구성요소를 표로 제시하고 목표·활동·수혜자의 관계를 짧게 설명한다."},
    "pdm": {"keywords": ["사업설계매트릭스", "PDM", "Narrative Summary", "검증수단", "중요가정"], "structure": "상위목표-성과-산출-활동의 수직 논리와 지표-MOV-가정의 수평 논리를 표로 검증한다."},
    "eval-purpose": {"keywords": ["평가의 목적과 범위", "평가 목적", "평가 범위", "평가 활용"], "structure": "평가 목적, 대상과 시간·공간 범위, 핵심 판단영역, 결과 활용주체를 구분한다."},
    "eval-matrix": {"keywords": ["평가매트릭스", "평가질문", "측정지표", "자료출처", "분석방법"], "structure": "각 평가질문에 관찰 가능한 지표, 실제 자료원과 적합한 분석방법을 일대일로 연결한다."},
    "eval-methods": {"keywords": ["평가 방법", "문헌조사", "혼합연구", "삼각검증", "면담", "설문조사"], "structure": "자료수집과 분석을 구분하고 표본·도구·교차검증 절차 및 실제 수행 범위를 투명하게 기술한다."},
    "eval-limitations": {"keywords": ["평가의 한계", "한계 및 보완", "자료의 한계", "편향", "완화"], "structure": "각 한계가 어떤 판단에 영향을 주는지와 적용한 완화조치, 잔여 불확실성을 함께 쓴다."},
    "eval-team": {"keywords": ["평가팀 구성", "시행체계", "품질관리", "역할"], "structure": "인력별 전문성·역할, 의사결정과 검토 절차, 이해상충과 품질관리 체계를 명시한다."},
    "achievement": {"keywords": ["성과 달성도", "성과지표", "목표치", "달성도", "기초선", "종료선"], "structure": "지표별 기초선·목표·실적·달성률·MOV와 차이 원인을 표와 해설로 제시한다."},
    "criteria-relevance": {"keywords": ["적절성", "수요", "우선순위", "사업설계", "정책 부합"], "structure": "평가질문별로 수요·정책·설계 근거를 교차하고 변화 대응의 적절성까지 논증한다."},
    "criteria-coherence": {"keywords": ["일관성", "내적 일관성", "외적 일관성", "상호보완", "시너지"], "structure": "내부 구성요소의 논리 정합성과 외부 정책·기관·사업과의 조정 및 부가가치를 구분한다."},
    "criteria-effectiveness": {"keywords": ["효과성", "산출물", "성과", "목표 달성", "수혜자 변화", "형평성"], "structure": "산출-성과-목표의 달성 증거와 기여요인·대안설명·형평성을 질문별로 분석한다."},
    "criteria-efficiency": {"keywords": ["효율성", "예산 집행", "일정", "투입 대비", "조달", "경제성"], "structure": "예산·시간·조달·관리 효율을 계획 대비 실적으로 비교하고 산출과의 관계를 설명한다."},
    "criteria-sustainability": {"keywords": ["지속가능성", "재정", "제도적", "조직", "주인의식", "유지관리"], "structure": "제도·조직·인력·재정·기술·사회적 지속성을 구분하고 위험과 책임주체를 명시한다."},
    "criteria-crosscutting": {"keywords": ["범분야", "성주류화", "젠더", "인권", "취약계층", "환경"], "structure": "설계 반영, 실제 참여와 편익, 분리통계, 부정적 영향과 세이프가드를 구분해 평가한다."},
    "criteria-other": {"keywords": ["그 외 평가기준", "혁신성", "확산 가능성", "특수성"], "structure": "사업 고유의 혁신성·확장성만 별도 기준으로 다루고 다른 DAC 기준과 중복하지 않는다."},
    "conclusion": {"keywords": ["결론", "종합 평가", "주요 성과", "한계", "제언"], "structure": "평가질문에 대한 최종 답, 가장 중요한 성과와 한계, 종합적 의미를 근거의 강도에 맞게 종합한다."},
    "working-factors": {"keywords": ["작동요인", "작동 요인", "성공 요인", "수요자 측", "공급자 측"], "structure": "성과에 기여한 메커니즘을 수요자·공급자·제도체계 수준으로 나누고 관찰 근거와 연결한다."},
    "nonworking-factors": {"keywords": ["비작동요인", "비작동 요인", "저해 요인", "제약 요인", "관리부실"], "structure": "성과경로를 약화한 조건과 원인을 수준별로 분석하고 책임 추궁보다 개선 가능한 지점을 도출한다."},
    "theory": {"keywords": ["변화이론", "Theory of Change", "성과경로", "To-Be", "가정"], "structure": "투입-활동-산출-성과-영향 경로별로 실제 작동 여부와 핵심 가정·외부요인을 검증한다."},
    "feedback": {"keywords": ["환류과제", "환류 과제", "후속사업", "이행부서", "선정 사유", "위험요인"], "structure": "관찰사항-실행조치-책임주체-기한·우선순위-기대효과-미이행 위험-확인자료를 한 행으로 연결한다."},
    "lessons": {"keywords": ["교훈", "Lessons Learned", "체크리스트", "유사 사업"], "structure": "사업 사례를 일반화 가능한 설계·수행 원칙으로 전환하고 M&E 점검질문을 붙인다."},
}

PARTS = {str(part["id"]): part for part in EDITOR_REPORT_PARTS}


def _clean_page(text: str) -> str:
    text = (text or "").replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _page_score(part_id: str, text: str, page_number: int) -> float:
    part = PARTS[part_id]
    guide = SECTION_GUIDANCE[part_id]
    head = text[:1200]
    score = 0.0
    for heading in part.get("sampleHeadings", []):
        if heading and re.search(rf"(?:^|\n)\s*(?:[ⅠⅡⅢⅣⅤⅥIVX]+[.장\s]*)?(?:\d+[.)]?\s*)?{re.escape(heading)}", head):
            score += 48
        elif heading and heading in head:
            score += 24
        elif heading and heading in text:
            score += 8
    for keyword in guide["keywords"]:
        count = text.count(keyword)
        score += min(count, 5) * 4
        if keyword in head:
            score += 5
    if len(text) >= 900:
        score += 8
    if page_number > 5:
        score += 3
    if text.count("···") >= 3 or text.count("……") >= 3:
        score -= 45
    if len(re.findall(r"\.{5,}", text)) >= 3:
        score -= 35
    if part_id.startswith("criteria-"):
        if "평가 등급 결과표" in head or "점수 산정 이유" in head:
            score -= 95
        if any(marker in head for marker in ("평가매트릭스", "평가 방법", "평가방법", "측정지표 자료출처 분석방법", "평가항목 평가질문")):
            score -= 90
        criterion_headings = {
            "criteria-relevance": r"(?:^|\n)\s*1\.\s*적절성",
            "criteria-coherence": r"(?:^|\n)\s*2\.\s*일관성",
            "criteria-effectiveness": r"(?:^|\n)\s*3\.\s*효과성",
            "criteria-efficiency": r"(?:^|\n)\s*4\.\s*효율성",
            "criteria-sustainability": r"(?:^|\n)\s*5\.\s*지속\s*가능성",
        }
        pattern = criterion_headings.get(part_id)
        if pattern and re.search(pattern, text):
            score += 55
    if part_id in {"working-factors", "nonworking-factors", "theory"}:
        if re.search(r"(?:^|\n)\s*2\.\s*작동\s*/?\s*비작동|작동요인\s*및\s*비작동", text):
            score += 50
        if "국문 요약" in head:
            score -= 100
    if part_id == "eval-methods" and re.search(r"(?:^|\n)\s*3\.\s*평가\s*방법", text):
        score += 55
    if part_id == "eval-methods" and any(marker in head for marker in ("평가매트릭스", "평가항목 평가질문", "측정지표 자료출처 분석방법")):
        score -= 85
    return score


def _best_excerpt(part_id: str, pages: list[str]) -> tuple[int, int, str, float] | None:
    ranked = sorted(
        ((_page_score(part_id, text, index + 1), index) for index, text in enumerate(pages)),
        reverse=True,
    )
    if not ranked or ranked[0][0] < 12:
        return None
    score, index = ranked[0]
    selected = [pages[index]]
    end = index
    # One following page usually captures the evidence and interpretation that
    # start after a heading, without flooding prompts with an entire report.
    if index + 1 < len(pages) and len(selected[0]) < 6000:
        selected.append(pages[index + 1])
        end = index + 1
    content = "\n\n".join(selected)
    content = content[:9000].strip()
    return index + 1, end + 1, content, score


def seed_reference_examples(sample_dir: Path = SAMPLE_DIR) -> dict:
    pdfs = sorted(sample_dir.glob("*.pdf"))
    seeded_sources = 0
    seeded_examples = 0
    for pdf_path in pdfs:
        payload = pdf_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        reader = PdfReader(pdf_path)
        pages = [_clean_page(page.extract_text() or "") for page in reader.pages]
        source_id = uuid.uuid5(uuid.NAMESPACE_URL, f"kodame-reference:{pdf_path.name}")
        project_title = re.sub(r"\s*(?:종료평가\s*)?결과보고서.*$", "", pdf_path.stem).strip() or pdf_path.stem
        with connection() as conn, conn.transaction():
            conn.execute(
                """INSERT INTO report_reference_sources
                   (id,file_name,project_title,source_path,page_count,content_sha256,metadata,updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,now())
                   ON CONFLICT(file_name) DO UPDATE SET project_title=excluded.project_title,
                     source_path=excluded.source_path,page_count=excluded.page_count,
                     content_sha256=excluded.content_sha256,metadata=excluded.metadata,updated_at=now()
                   RETURNING id""",
                (source_id, pdf_path.name, project_title, str(pdf_path), len(pages), digest,
                 Jsonb({"kind": "completed_oda_evaluation_report", "reference_use": "structure_and_reasoning_only"})),
            )
            conn.execute("DELETE FROM report_reference_examples WHERE source_id=%s", (source_id,))
            for part_id, part in PARTS.items():
                excerpt = _best_excerpt(part_id, pages)
                if not excerpt:
                    continue
                page_start, page_end, content, relevance = excerpt
                content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                tags = ["완성본", "전문가문체", "근거-해석", "구조참고"]
                conn.execute(
                    """INSERT INTO report_reference_examples
                       (source_id,part_id,section_title,page_start,page_end,content,structure_notes,
                        quality_tags,relevance_score,content_sha256)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (source_id, part_id, part["title"], page_start, page_end, content,
                     SECTION_GUIDANCE[part_id]["structure"], Jsonb(tags), relevance, content_digest),
                )
                seeded_examples += 1
        seeded_sources += 1
    return {"sources": seeded_sources, "examples": seeded_examples}


def reference_examples(
    part_id: str,
    limit: int = 3,
    max_chars: int = 4200,
    *,
    include_content: bool = True,
) -> list[dict]:
    """Return completed-report references for one logical section.

    Report generation requests metadata only.  Raw sample prose is selected
    solely for explicit inspection/seeding use so another project's facts
    cannot enter a generation prompt by accident.
    """
    content_column = "e.content" if include_content else "NULL::text AS content"
    source_columns = (
        "s.file_name,s.project_title"
        if include_content else
        "NULL::text AS file_name,NULL::text AS project_title"
    )
    with connection() as conn:
        rows = conn.execute(
            f"""SELECT e.id,e.part_id,e.page_start,e.page_end,{content_column},e.structure_notes,
                      e.quality_tags,e.relevance_score,{source_columns}
               FROM report_reference_examples e
               JOIN report_reference_sources s ON s.id=e.source_id
               WHERE e.part_id=%s ORDER BY e.relevance_score DESC,s.file_name LIMIT %s""",
            (part_id, limit),
        ).fetchall()
    result = []
    for row in rows:
        item = {**row, "id": int(row["id"]), "relevance_score": float(row["relevance_score"])}
        if include_content:
            item["content"] = str(row["content"] or "")[:max_chars]
        else:
            item.pop("content", None)
            item.pop("file_name", None)
            item.pop("project_title", None)
        result.append(item)
    return result


def reference_stats() -> dict:
    with connection() as conn:
        source_count = conn.execute("SELECT count(*) AS count FROM report_reference_sources").fetchone()["count"]
        rows = conn.execute(
            """SELECT part_id,count(*) AS examples,count(DISTINCT source_id) AS sources
               FROM report_reference_examples GROUP BY part_id ORDER BY part_id"""
        ).fetchall()
    return {"source_count": source_count, "example_count": sum(row["examples"] for row in rows), "by_part": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-dir", default=str(SAMPLE_DIR))
    args = parser.parse_args()
    open_pool()
    try:
        print(seed_reference_examples(Path(args.sample_dir)))
        print(reference_stats())
    finally:
        pool.close()


if __name__ == "__main__":
    main()
