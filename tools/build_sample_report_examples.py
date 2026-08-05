from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "samples"
OUTPUT_PATH = DATA_DIR / "sample_analysis" / "nepal_mugu_27_sections.json"
RAW_TEXT_PATH = DATA_DIR / "sample_analysis" / "nepal_mugu_full_text.txt"
RHWP_BIN = "rhwp"


PARTS = [
    ("cover", "title", "(1) 표지", ["종료평가 결과보고서"]),
    ("toc", "toc", "(2) 목차 및 작성 쪽수", ["| Ⅰ. 평가결과 요약", "Ⅰ. 평가결과 요약 <br> 1. 평가 등급 결과표", "목 차", "목차"]),
    ("notice", "notice", "(3) 평가보고서 관련 공지", ["평가보고서 관련 공지"]),
    ("grade", "grade", "(4) 평가등급 결과표", ["평가 등급 결과표", "평가등급 결과표"]),
    ("summary-ko", "summary", "(5) I. 평가결과 요약 1. 국문 요약", ["Ⅰ. 평가결과 요약", "I. 평가결과 요약", "평가결과 요약"]),
    ("project-background", "project-background", "(6) II. 대상사업개요 1. 사업 추진배경", ["1. 사업 추진배경", "1. 사업추진배경"]),
    ("project-overview", "project-overview", "(7) II. 대상사업개요 2. 사업개요", ["2. 사업 개요", "2. 사업개요"]),
    ("pdm", "pdm", "(8) II. 대상사업개요 3. 사업설계매트릭스(PDM)", ["3. 사업설계매트릭스", "사업설계매트릭스", "PDM"]),
    ("eval-purpose", "eval-purpose", "(9) III. 평가개요 1. 평가의 목적과 범위", ["1. 평가의 목적과 범위", "평가의 목적과 범위"]),
    ("eval-matrix", "eval-matrix", "(10) III. 평가개요 2. 평가매트릭스", ["2. 평가매트릭스", "평가매트릭스", "Evaluation Matrix"]),
    ("eval-methods", "eval-methods", "(11) III. 평가개요 3. 평가방법", ["3. 평가 방법", "3. 평가방법", "평가 방법"],
    ),
    ("eval-limitations", "eval-limitations", "(12) III. 평가개요 4. 평가의 한계", ["4. 평가의 한계", "평가의 한계"]),
    ("eval-team", "eval-team", "(13) III. 평가개요 5. 평가팀 구성 및 시행체계", ["5. 평가팀 구성", "평가팀 구성", "시행체계"]),
    ("achievement", "achievement", "(14) IV. 성과 달성도", ["1. 성과달성 요약표"]),
    ("criteria-relevance", "criteria-relevance", "(15) V. 기준별 평가결과 1. 적절성", ["1. 적절성", "적절성"]),
    ("criteria-coherence", "criteria-coherence", "(16) V. 기준별 평가결과 2. 일관성", ["2. 일관성", "일관성"]),
    ("criteria-effectiveness", "criteria-effectiveness", "(17) V. 기준별 평가결과 3. 효과성", ["3. 효과성", "효과성"]),
    ("criteria-efficiency", "criteria-efficiency", "(18) V. 기준별 평가결과 4. 효율성", ["4. 효율성", "효율성"]),
    ("criteria-sustainability", "criteria-sustainability", "(19) V. 기준별 평가결과 5. 지속가능성", ["5. 지속가능성", "지속가능성"]),
    ("criteria-crosscutting", "criteria-crosscutting", "(20) V. 기준별 평가결과 6. 범분야 이슈", ["6. 범분야", "범분야 이슈", "범분야"]),
    ("criteria-other", "criteria-other", "(21) V. 기준별 평가결과 7. 그 외 평가기준", ["7. 그 외 평가기준", "그 외 평가기준", "기타 평가기준"]),
    ("conclusion", "conclusion", "(22) VI. 결론 1. 결론", ["❍ (DAC 6대 기준에 따른 평가결과)", "❍ (사업 목표 달성)", "ㅇ 결론", "바. 결론과 제언"]),
    ("working-factors", "working-factors", "(23) VI. 결론 2. 작동요인 및 비작동요인 (1) 작동 요인", ["(1) 작동 요인", "작동 요인", "작동요인"]),
    ("nonworking-factors", "nonworking-factors", "(24) VI. 결론 2. 작동요인 및 비작동요인 (2) 비작동 요인", ["(2) 비작동 요인", "비작동 요인", "비작동요인"]),
    ("theory", "theory", "(25) VI. 결론 2. 작동요인 및 비작동요인 (3) 변화이론 분석", ["2. 사업 변화이론 분석", "(3) 변화이론 분석", "사업 변화이론 분석"]),
    ("feedback", "feedback", "(26) VI. 결론 3. 환류과제 및 교훈 (1) 환류과제", ["(1) 환류과제", "환류과제", "제언"]),
    ("lessons", "lessons", "(27) VI. 결론 3. 환류과제 및 교훈 (2) 교훈", ["2. 교훈", "ㅇ 교훈", "(2) 교훈", "Lessons Learned"]),
]


def normalize_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[\u0000-\u0008\u000b-\u001f]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_hwp_text(path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="sample_hwp_") as tmp:
        tmp_path = Path(tmp)
        for command in ("export-markdown", "export-text"):
            out_dir = tmp_path / command
            result = subprocess.run(
                [RHWP_BIN, command, str(path), "-o", str(out_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=60,
            )
            if result.returncode != 0:
                continue
            files = sorted(out_dir.glob("*.md")) + sorted(out_dir.glob("*.txt"))
            text = "\n\n".join(file.read_text(encoding="utf-8", errors="replace") for file in files)
            text = normalize_text(text)
            if len(text) > 1000:
                return text
        result = subprocess.run(
            [RHWP_BIN, "dump", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        return normalize_text(result.stdout)


def find_marker(text: str, markers: list[str], start: int = 0) -> tuple[int, str]:
    candidates: list[tuple[int, str]] = []
    for marker in markers:
        index = text.find(marker, start)
        if index >= 0:
            candidates.append((index, marker))
    if not candidates:
        return -1, ""
    return min(candidates, key=lambda item: item[0])


def compress_section_text(text: str, limit: int = 9000) -> str:
    text = normalize_text(text)
    text = re.sub(r"\n\s*(?=\n)", "\n", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def split_sections(text: str) -> list[dict]:
    starts: list[dict] = []
    cursor = 0
    allow_global_fallback = {"criteria-other", "theory", "lessons"}
    for index, (part_id, section_id, title, markers) in enumerate(PARTS):
        search_start = cursor
        if part_id == "cover":
            found_index, found_marker = find_marker(text, markers, 0)
        else:
            found_index, found_marker = find_marker(text, markers, search_start)
        if found_index < 0 and part_id in allow_global_fallback:
            found_index, found_marker = find_marker(text, markers, 0)
        starts.append({
            "order": index + 1,
            "partId": part_id,
            "sectionId": section_id,
            "title": title,
            "start": found_index,
            "marker": found_marker,
        })
        if found_index >= 0:
            cursor = max(cursor, found_index + len(found_marker))

    start_lookup = {item["partId"]: item["start"] for item in starts}
    markers_by_part = {part_id: markers for part_id, _section_id, _title, markers in PARTS}
    constrained_fallbacks = {
        "achievement": "eval-team",
        "theory": "achievement",
        "conclusion": "criteria-crosscutting",
        "lessons": "conclusion",
    }
    anchor_by_part = {
        "achievement": "\n-17-\n",
        "conclusion": "\n-43-\n",
        "lessons": "\n-44-\n",
        "feedback": "\n-44-\n",
    }
    for item in starts:
        after_part = constrained_fallbacks.get(item["partId"])
        after_start = start_lookup.get(after_part or "", -1)
        if after_start >= 0 and item["start"] < after_start:
            found_index, found_marker = find_marker(text, markers_by_part[item["partId"]], after_start)
            if found_index >= 0:
                item["start"] = found_index
                item["marker"] = found_marker
        anchor = anchor_by_part.get(item["partId"])
        if anchor:
            anchor_index = text.find(anchor)
            if anchor_index >= 0 and item["start"] < anchor_index:
                found_index, found_marker = find_marker(text, markers_by_part[item["partId"]], anchor_index)
                if found_index >= 0:
                    item["start"] = found_index
                    item["marker"] = found_marker

    found_starts = [item for item in starts if item["start"] >= 0]
    found_starts.sort(key=lambda item: item["start"])
    end_by_part = {}
    for current, next_item in zip(found_starts, found_starts[1:]):
        end_by_part[current["partId"]] = next_item["start"]
    if found_starts:
        end_by_part[found_starts[-1]["partId"]] = len(text)
    start_by_part = {item["partId"]: item["start"] for item in found_starts}
    if start_by_part.get("lessons", -1) >= 0 and start_by_part.get("feedback", -1) > start_by_part.get("lessons", -1):
        end_by_part["lessons"] = start_by_part["feedback"]

    sections = []
    for item in starts:
        start = item["start"]
        if start < 0:
            if item["partId"] == "criteria-other":
                body = (
                    "이 실제 작성 보고서는 V. 기준별 평가결과에서 적절성, 일관성, 효과성, 효율성, "
                    "지속가능성, 범분야 이슈까지만 별도 절로 다루고, '그 외 평가기준' 절은 별도로 두지 않음. "
                    "따라서 해당 파트는 사업 특수 기준이 실제로 있을 때만 작성하고, 없으면 해당 없음 사유를 간단히 쓰는 예시로 활용한다."
                )
                status = "not_applicable_in_source"
            else:
                body = ""
                status = "missing"
        else:
            body = text[start:end_by_part.get(item["partId"], len(text))]
            status = "ok"
        body = compress_section_text(body)
        sections.append({
            "order": item["order"],
            "partId": item["partId"],
            "sectionId": item["sectionId"],
            "title": item["title"],
            "matchedHeading": item["marker"],
            "status": status,
            "charCount": len(body),
            "exampleText": body,
        })
    return sections


def build_payload(source_path: Path) -> dict:
    text = extract_hwp_text(source_path)
    DATA_DIR.joinpath("sample_analysis").mkdir(parents=True, exist_ok=True)
    RAW_TEXT_PATH.write_text(text, encoding="utf-8")
    sections = split_sections(text)
    return {
        "source": {
            "fileName": source_path.name,
            "path": str(source_path),
            "builtAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rawTextPath": str(RAW_TEXT_PATH.relative_to(ROOT)),
            "note": "실제 사람이 작성한 종료평가보고서를 27개 작성 파트별 좋은 예시로 분할한 RAG 자료. 문장 복사 금지, 구조/밀도/문체 참고용.",
        },
        "sections": sections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=str(SAMPLES_DIR / "네팔 무구 최종 수정본(1220 정애숙).hwp"),
        help="sample HWP/HWPX report path",
    )
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()
    source_path = Path(args.source)
    output_path = Path(args.output)
    payload = build_payload(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "rawText": str(RAW_TEXT_PATH),
        "sections": len(payload["sections"]),
        "ok": sum(1 for item in payload["sections"] if item["status"] == "ok"),
        "missing": [item["partId"] for item in payload["sections"] if item["status"] != "ok"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
