from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from report_few_shot import (
    EXPECTED_PART_IDS,
    FORMAT_ONLY_DEMOS,
    build_format_only_few_shot_messages,
    few_shot_artifact_issues,
    format_only_sample_reference,
    validate_format_only_few_shot_catalog,
)
from report_prompts import EDITOR_REPORT_PARTS
from kodame_intake.report_generator import _call_json, _reference_context
from kodame_intake.report_references import reference_examples


class ReportFewShotTests(unittest.TestCase):
    def test_all_27_sections_have_unique_two_shot_format_examples(self) -> None:
        validate_format_only_few_shot_catalog()
        self.assertEqual(len(EXPECTED_PART_IDS), 27)
        self.assertEqual(len(FORMAT_ONLY_DEMOS), 27)
        self.assertEqual(len(set(FORMAT_ONLY_DEMOS.values())), 27)
        for part_id in EXPECTED_PART_IDS:
            messages = build_format_only_few_shot_messages(
                part_id,
                structure_notes="형식 구조만 사용",
                sample_count=5,
                output_key="content",
            )
            self.assertEqual([item["role"] for item in messages], ["user", "assistant", "user", "assistant"])
            self.assertTrue(all(item["content"].strip() for item in messages))
            self.assertIn('"raw_sample_content_in_prompt": false', messages[0]["content"])

    def test_every_runtime_section_prompt_requires_few_shot_isolation(self) -> None:
        self.assertEqual(len(EDITOR_REPORT_PARTS), 27)
        for part in EDITOR_REPORT_PARTS:
            prompt = str(part.get("prompt") or "")
            self.assertIn("[필수 Few-shot 생성 규칙]", prompt, part.get("id"))
            self.assertIn("샘플 원문", prompt, part.get("id"))
            self.assertIn("근접 패러프레이즈", prompt, part.get("id"))

    def test_raw_completed_report_content_cannot_enter_generation_reference_context(self) -> None:
        raw_fact = "FORBIDDEN_SAMPLE_COUNTRY_AND_SCORE_98765"
        safe = _reference_context([{
            "id": 1,
            "content": raw_fact,
            "structure_notes": "주장-근거-해석 순서",
            "quality_tags": ["구조참고"],
            "relevance_score": 99.0,
        }])
        self.assertNotIn(raw_fact, json.dumps(safe, ensure_ascii=False))
        legacy_safe = format_only_sample_reference(
            "criteria-effectiveness",
            structure_notes="산출-성과-기여요인 순서",
            sample_count=5,
        )
        self.assertNotIn(raw_fact, legacy_safe)
        self.assertIn('"raw_sample_content_in_prompt": false', legacy_safe)

    def test_few_shot_placeholders_are_rejected_from_saved_report_text(self) -> None:
        self.assertTrue(few_shot_artifact_issues("{{CURRENT_PROJECT_TITLE}}"))
        self.assertTrue(few_shot_artifact_issues("{{CURRENT_EVIDENCE_ONLY_SCORE}}"))
        self.assertEqual(few_shot_artifact_issues("현재 사업의 확인된 성과를 기술함."), [])

    def test_generation_call_places_two_shots_before_the_current_project_request(self) -> None:
        captured: dict = {}

        class FakeResponse:
            status_code = 200
            text = ""

            @staticmethod
            def json() -> dict:
                return {
                    "choices": [{"message": {"content": '{"content":"완료"}'}}],
                    "usage": {},
                }

        class FakeClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            @staticmethod
            def post(url, *, headers, json):
                captured["messages"] = json["messages"]
                return FakeResponse()

        shots = build_format_only_few_shot_messages(
            "conclusion",
            structure_notes="종합 판단-한계-후속 방향",
            sample_count=5,
            output_key="content",
        )
        with (
            patch("kodame_intake.report_generator.httpx.Client", FakeClient),
            patch("kodame_intake.ai_gateway.OPENROUTER_API_KEY", "fake-test-key"),
            patch("kodame_intake.ai_gateway.record_token_usage"),
        ):
            result = _call_json(
                "system",
                "CURRENT_PROJECT_REQUEST",
                "test",
                0.0,
                few_shot_messages=shots,
            )
        self.assertEqual(result["content"], "완료")
        self.assertEqual(
            [item["role"] for item in captured["messages"]],
            ["system", "user", "assistant", "user", "assistant", "user"],
        )
        self.assertEqual(captured["messages"][-1]["content"], "CURRENT_PROJECT_REQUEST")

    def test_generation_reference_query_does_not_select_or_return_sample_prose(self) -> None:
        captured: dict = {}

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            @staticmethod
            def execute(query, params):
                captured["query"] = query

                class Rows:
                    @staticmethod
                    def fetchall():
                        return [{
                            "id": 7,
                            "part_id": "conclusion",
                            "page_start": 1,
                            "page_end": 2,
                            "content": None,
                            "structure_notes": "종합 판단-한계-후속 방향",
                            "quality_tags": ["구조참고"],
                            "relevance_score": 90,
                            "file_name": "sample.pdf",
                            "project_title": "sample",
                        }]

                return Rows()

        with patch("kodame_intake.report_references.connection", lambda: FakeConnection()):
            rows = reference_examples("conclusion", include_content=False)
        self.assertIn("NULL::text AS content", captured["query"])
        self.assertNotIn("content", rows[0])
        self.assertNotIn("file_name", rows[0])
        self.assertNotIn("project_title", rows[0])


if __name__ == "__main__":
    unittest.main()
