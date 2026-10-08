from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch

from kodame_intake.localized_views import (
    TextSlot,
    ViewTranslationError,
    _cache_safe_payload,
    _translate_batch,
    collect_text_slots,
    localize_project_views,
)
from kodame_intake.openrouter import AnalysisError


class LocalizedViewsTests(unittest.TestCase):
    def sample_views(self) -> dict:
        return {
            "dashboard": {
                "project": {"name": "응급구조학과 구축 사업", "country": "우즈베키스탄"},
                "workflow_status": {"code": "review_required", "message": "보완 2건 검토 필요"},
            },
            "project_overview": {
                "overview": {
                    "objective": {"text": "병원 전 응급의료 역량을 강화한다.", "source_refs": ["D001"]}
                },
                "pdm_source_document": {"id": "doc-1", "file_name": "최신_PDM.hwpx"},
            },
            "pdm": {
                "tiers": [{
                    "id": "impact",
                    "name": "영향",
                    "indicators": [{"id": "I1", "code": "I-1", "text": "사망률 감소"}],
                }],
            },
            "evaluation": {
                "criteria": [{"id": "relevance", "name": "적절성", "score": 4}],
            },
        }

    def test_collects_human_text_without_contract_identifiers_or_file_names(self) -> None:
        slots = collect_text_slots(self.sample_views())
        sources = {slot.source for slot in slots}
        self.assertIn("응급구조학과 구축 사업", sources)
        self.assertIn("병원 전 응급의료 역량을 강화한다.", sources)
        self.assertNotIn("review_required", sources)
        self.assertNotIn("doc-1", sources)
        self.assertNotIn("최신_PDM.hwpx", sources)
        self.assertNotIn("I-1", sources)

    @patch("kodame_intake.localized_views._store_translation")
    @patch("kodame_intake.localized_views._cached_translation", return_value=None)
    @patch("kodame_intake.localized_views._translate_batch")
    def test_translates_all_display_slots_and_preserves_contract_values(
        self,
        translate_batch,
        _cached,
        _store,
    ) -> None:
        def translated(batch, _locale, _source_locale):
            return ({slot.key: f"EN::{slot.source}" for slot in batch}, "test-model")

        translate_batch.side_effect = translated
        result = localize_project_views(self.sample_views(), locale="en", source_locale="ko")
        views = result["views"]
        self.assertEqual(result["translation_status"], "generated")
        self.assertEqual(views["dashboard"]["project"]["name"], "EN::응급구조학과 구축 사업")
        self.assertEqual(views["pdm"]["tiers"][0]["indicators"][0]["text"], "EN::사망률 감소")
        self.assertEqual(views["evaluation"]["criteria"][0]["name"], "EN::적절성")
        self.assertEqual(views["dashboard"]["workflow_status"]["code"], "review_required")
        self.assertEqual(views["project_overview"]["pdm_source_document"]["file_name"], "최신_PDM.hwpx")
        self.assertEqual(views["pdm"]["tiers"][0]["indicators"][0]["code"], "I-1")
        self.assertEqual(views["evaluation"]["criteria"][0]["score"], 4)
        _store.assert_called_once()

    @patch("kodame_intake.localized_views._cached_translation", return_value=None)
    @patch("kodame_intake.localized_views._translate_batch")
    def test_rejects_incomplete_translation_instead_of_showing_mixed_languages(
        self,
        translate_batch,
        _cached,
    ) -> None:
        translate_batch.return_value = ({}, "test-model")
        with self.assertRaises(ViewTranslationError):
            localize_project_views(self.sample_views(), locale="en", source_locale="ko")

    def test_cache_payload_normalizes_database_uuid_and_datetime_values(self) -> None:
        document_id = UUID("cb860180-08d0-4bbb-8098-0e15ec2d9b8e")
        created_at = datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc)
        result = _cache_safe_payload({"document_id": document_id, "created_at": created_at})
        self.assertEqual(result["document_id"], str(document_id))
        self.assertEqual(result["created_at"], "2026-09-02T09:30:00+00:00")

    @patch("kodame_intake.localized_views._request_json")
    def test_translation_batch_retries_invalid_json_and_requires_every_key(self, request_json) -> None:
        request_json.side_effect = [
            AnalysisError("invalid JSON"),
            ({"translations": {"t0001": "Project objective"}}, "test-model"),
        ]
        values, model = _translate_batch(
            [TextSlot(key="t0001", path=("project_overview", "objective"), source="사업목적")],
            "en",
            "ko",
        )
        self.assertEqual(values, {"t0001": "Project objective"})
        self.assertEqual(model, "test-model")
        self.assertEqual(request_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
