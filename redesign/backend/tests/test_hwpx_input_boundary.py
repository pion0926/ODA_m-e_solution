from __future__ import annotations

import json
from pathlib import Path
import random
import unittest
import zipfile
import xml.etree.ElementTree as ET

from backend.oda_me.reports.context import STRUCTURED_SECTION_SLOT_KEYS, STRUCTURED_SECTION_SCHEMAS, normalize_lessons_section
from backend.oda_me.hwpx.patchers import get_hwpx_xml_scope_text, parse_lesson_items, patch_hwpx_lessons_table_xml, find_hwpx_tag_spans, hwpx_escape_text, normalize_hwpx_table_value
from kodame_intake.hwpx_adapters.registry import ADAPTER_BY_PART
from kodame_intake.hwpx_adapters.structured_input import MISSING_SLOT_TEXT, read_slot_input
from kodame_intake.hwpx_pipeline import normalize_section_text, _background_slots, _overview_slots


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "samples" / "5-1. 종료평가 결과보고서 placeholder.hwpx"


def payload(part, values):
    return json.dumps({"schema": STRUCTURED_SECTION_SCHEMAS[part], "slots": values}, ensure_ascii=False)


def prepare(part, source):
    normalized, report = normalize_section_text(part, source)
    prepared = ADAPTER_BY_PART[part].prepare({"project": {"title": "새 사업"}}, {part: source}, {part: normalized}, [])
    return json.loads(prepared)["slots"], report


class HwpxInputBoundaryTests(unittest.TestCase):
    def test_every_structured_adapter_preserves_every_complete_value(self):
        for part, keys in STRUCTURED_SECTION_SLOT_KEYS.items():
            values = {key: f"항목 {index} 본문임. " + "검증된 원문을 생략하지 않음. " * 40 for index, key in enumerate(keys)}
            with self.subTest(part=part):
                actual, report = prepare(part, payload(part, values))
                self.assertEqual(actual, values)
                self.assertTrue(report["structured_input"])

    def test_serialization_variants_preserve_prose_without_inventing_facts(self):
        part = "project-background"
        values = {key: f"({index}번째 배경) 콤마 , }} 및 <문자>와 밑줄_a를 그대로 보존함." for index, key in enumerate(STRUCTURED_SECTION_SLOT_KEYS[part])}
        canonical = payload(part, values)
        doc = json.loads(canonical)
        variants = [canonical, json.dumps(canonical, ensure_ascii=False), json.dumps({"content": canonical}, ensure_ascii=False), json.dumps({"revised_content": doc}, ensure_ascii=False), f"```json\n{canonical}\n```", f"요청한 결과입니다.\n{canonical}\n이상입니다.", canonical[:-1] + ",}", repr(doc),
                    json.dumps({"schema": doc["schema"].replace("_", " "), "slots": {k.replace("_", " "): v for k, v in values.items()}}, ensure_ascii=False)]
        for source in variants:
            with self.subTest(source=source[:60]):
                self.assertEqual(read_slot_input(part, source).complete(list(values)), values)
                self.assertEqual(prepare(part, source)[0], values)

    def test_partial_payload_is_explicit_gap_not_repeated_neighbor(self):
        part = "project-background"
        keys = STRUCTURED_SECTION_SLOT_KEYS[part]
        actual, report = prepare(part, payload(part, {keys[0]: "(첫 항목) 유일한 확인 내용임."}))
        self.assertEqual(actual[keys[0]], "(첫 항목) 유일한 확인 내용임.")
        self.assertEqual([actual[key] for key in keys[1:]], [MISSING_SLOT_TEXT] * 4)
        self.assertTrue(report["warnings"])

    def test_truncated_json_keeps_completed_values_and_remaining_text(self):
        part = "eval-purpose"
        source = '{"schema":"section9_eval_purpose_slots_v1","slots":{"evaluation_purpose_scope_body":"잘린 응답에서도 원문을 보존함.'
        actual, report = prepare(part, source)
        self.assertEqual(actual["evaluation_purpose_scope_body"], "잘린 응답에서도 원문을 보존함.")
        self.assertTrue(report["warnings"])

    def test_nonstring_or_unknown_values_remain_reviewable(self):
        part = "eval-purpose"
        key = STRUCTURED_SECTION_SLOT_KEYS[part][0]
        actual, report = prepare(part, payload(part, {key: ["첫 본문", "둘째 본문"], "unexpected": "추가 원문"}))
        self.assertIn("첫 본문\n둘째 본문", actual[key])
        self.assertIn("추가 원문", actual[key])
        self.assertTrue(report["warnings"])

    def test_preprocessing_never_exposes_machine_keys_to_reader(self):
        source = payload("project-background", {key: "(제목) 현재 프로젝트 본문임." for key in STRUCTURED_SECTION_SLOT_KEYS["project-background"]})
        normalized, _ = normalize_section_text("project-background", source)
        self.assertNotIn("schema", normalized)
        self.assertNotIn("slots", normalized)
        self.assertNotIn("koica_policy_alignment", normalized)
        self.assertIn("현재 프로젝트 본문임", normalized)

    def test_legacy_background_does_not_truncate_or_drop_sixth_group(self):
        body = "원문 보존 문장임. " * 70
        source = "\n\n".join(f"({i}번째 배경)\n{body}{i} 마지막 문장임." for i in range(6))
        actual = "\n".join(_background_slots(source).values())
        for i in range(6):
            self.assertIn(f"{i} 마지막 문장임.", actual)

    def test_legacy_background_has_no_synthetic_duplicate_title(self):
        for first in ("ㅇ (현지 개발문제) 원문임.", "(현지 개발문제) 원문임.", "ㅇ 현지 개발문제\n- 원문임."):
            actual = next(iter(_background_slots(first).values()))
            self.assertTrue(actual.startswith("(현지 개발문제)"))
            self.assertNotIn("개발문제와 구조적 취약성", actual)
            self.assertNotIn("ㅇ", actual)

    def test_legacy_twelve_overview_values_remain_in_slot_order(self):
        lines = [(f"▣ {i} 원문 " + "검토내용 " * 60).strip() for i in range(12)]
        self.assertEqual(list(_overview_slots({}, "\n".join(lines), "다른 본문").values()), lines)

    def test_lesson_fields_are_not_rows_and_long_body_is_not_cut(self):
        body = "작성된 교훈 본문을 보존함. " * 50
        raw = "\n\n".join(f"ㅇ 교훈 제목 {i}\n- {body}{i} 마지막 문장임.\n- 분야: 일반\n- 이전년도 교훈 중복 여부: 확인 중\n- 체크리스트 질문: 질문 {i}?" for i in range(4))
        for value in (raw, normalize_lessons_section(raw)):
            rows = parse_lesson_items(value)
            self.assertEqual(len(rows), 4)
            for i, row in enumerate(rows):
                self.assertEqual(row["observation"], f"교훈 제목 {i}")
                self.assertIn(f"{i} 마지막 문장임.", row["lesson"])
                self.assertEqual(row["checklist"], f"질문 {i}?")
                self.assertEqual(row["duplicate"], "확인 중")
                self.assertNotIn("분야:", row["lesson"])

    def test_missing_lesson_metadata_is_not_invented(self):
        row = parse_lesson_items("ㅇ 현지 협력\n- 확인된 교훈임.")[0]
        self.assertEqual(row["duplicate"], "확인 필요")
        self.assertEqual(row["category"], "미기재")
        self.assertIn("작성되지 않아", row["checklist"])

    def test_extra_lesson_rows_are_kept_in_xml(self):
        with zipfile.ZipFile(TEMPLATE) as archive:
            xml = archive.read("Contents/section8.xml").decode("utf-8")
        raw = "\n".join(f"ㅇ 교훈 제목 {i}\n- 보존할 교훈 {i}\n- 체크리스트 질문: 질문 {i}?" for i in range(9))
        result = patch_hwpx_lessons_table_xml(xml, {"lessons": raw})
        ET.fromstring(result)
        for i in range(9):
            self.assertIn(f"보존할 교훈 {i}", result)

    def test_new_project_theory_never_inserts_previous_project_path(self):
        source = "ㅇ 식수 접근성 경로\n- 우물 설치로 식수 접근성을 개선함."
        actual, _ = normalize_section_text("theory", source)
        self.assertNotIn("응급", actual)
        self.assertNotIn("학과", actual)
        self.assertIn("우물 설치", actual)

    def test_invalid_xml_characters_cannot_corrupt_the_package(self):
        bad = "앞 본문\x00\x08\ud800\uffff 뒤 본문 <태그> & 문자"
        escaped = hwpx_escape_text(bad)
        node = ET.fromstring(f"<text>{escaped}</text>")
        self.assertIn("앞 본문", node.text)
        self.assertIn("뒤 본문 <태그> & 문자", node.text)
        self.assertEqual(node.text.count("\ufffd"), 4)

    def test_long_table_values_are_not_silently_shortened(self):
        source = "장문 근거임. " * 1600 + "마지막 근거도 반드시 보존함."
        self.assertEqual(normalize_hwpx_table_value(source, 220), source)
        self.assertEqual(normalize_hwpx_table_value(source, 10000), source)

    def test_narrative_budget_is_warning_not_content_truncation(self):
        source = "ㅇ 근거 검토\n- " + "원문 보존 근거임. " * 1100 + "마지막 결론을 보존함."
        normalized, report = normalize_section_text("eval-limitations", source, 500)
        self.assertIn("마지막 결론을 보존함.", normalized)
        self.assertTrue(report["over_budget"])
        self.assertFalse(report["truncated"])
        self.assertTrue(any("전체 본문을 보존" in warning for warning in report["warnings"]))

    def test_randomized_slot_prose_is_byte_preserved_through_prepare(self):
        rng = random.Random(912)
        alphabet = '가나다라마바사 0123456789_\\"{}[]&<>\n\t.,'
        for part, keys in STRUCTURED_SECTION_SLOT_KEYS.items():
            for _ in range(10):
                values = {key: "원문 " + "".join(rng.choice(alphabet) for _ in range(140)) for key in keys}
                actual, _ = prepare(part, payload(part, values))
                self.assertEqual(actual, values, part)

    def test_actual_knut_background_and_lessons_regression(self):
        snapshot = ROOT / "output/knut-e2e-20260911/recovered.json"
        if not snapshot.exists():
            self.skipTest("KNUT private test snapshot is not shipped with the runtime")
        sections = {item["part_id"]: item["content"] for item in json.loads(snapshot.read_text(encoding="utf-8"))["report/sections"]["body"]["items"]}
        original = json.loads(sections["project-background"])["slots"]
        actual, _ = prepare("project-background", sections["project-background"])
        self.assertEqual(actual, original)
        adapter = ADAPTER_BY_PART["project-background"]
        with zipfile.ZipFile(TEMPLATE) as archive:
            xml = archive.read(adapter.spec.hwpx_path).decode("utf-8")
        xml = adapter.patch_xml(xml, {"project": {}}, {"project-background": payload("project-background", actual)}).xml
        ET.fromstring(xml)
        visible = get_hwpx_xml_scope_text(xml)
        self.assertNotIn("section6_project_background_slots_v1", visible)
        for value in original.values():
            # Background slots intentionally split the title into its own
            # styled paragraph. Check the entire substantive body, not a token.
            self.assertIn(value.split(") ", 1)[1], visible)
        rows = parse_lesson_items(sections["lessons"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["observation"], "현지 거버넌스 기반 협력 체계 구축")
        self.assertIn("1차년도 자체평가결과보고서", rows[0]["lesson"])
        self.assertEqual(rows[-1]["category"], "일반")

    def test_actual_knut_matrix_values_reach_all_fixed_cells(self):
        snapshot = ROOT / "output/knut-e2e-20260911/recovered.json"
        if not snapshot.exists():
            self.skipTest("KNUT private test snapshot is not shipped with the runtime")
        sections = {item["part_id"]: item["content"] for item in json.loads(snapshot.read_text(encoding="utf-8"))["report/sections"]["body"]["items"]}
        original = json.loads(sections["eval-matrix"])["slots"]
        actual, _ = prepare("eval-matrix", sections["eval-matrix"])
        self.assertEqual(actual, original)
        adapter = ADAPTER_BY_PART["eval-matrix"]
        with zipfile.ZipFile(TEMPLATE) as archive:
            xml = archive.read(adapter.spec.hwpx_path).decode("utf-8")
        xml = adapter.patch_xml(xml, {"project": {}}, {"eval-matrix": payload("eval-matrix", actual)}).xml
        ET.fromstring(xml)
        visible = get_hwpx_xml_scope_text(xml)
        self.assertNotIn("section10_eval_matrix_slots_v1", visible)
        for value in original.values():
            self.assertIn(value, visible)


if __name__ == "__main__":
    unittest.main()
