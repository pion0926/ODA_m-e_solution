from __future__ import annotations

import unittest
from pathlib import Path

from report_prompts import (
    EDITOR_PART_REFERENCE_PIPELINES,
    EDITOR_REPORT_PARTS,
    literal_from_prompt_file,
    prompt_file_for_part,
)
from kodame_intake.hwpx_adapters import ADAPTER_BY_PART, SECTION_ADAPTERS
from kodame_intake.hwpx_pipeline import (
    AUTHORING_SHAPES,
    SECTION_PIPELINES,
    hwpx_authoring_contract,
    validate_hwpx_pipeline_contracts,
)
from kodame_intake.report_sections import section_reference_route, validate_report_section_contracts
from report_outline import NARRATIVE_OUTLINE_PART_IDS
from report_few_shot import FORMAT_ONLY_DEMOS


class ReportSectionContractTests(unittest.TestCase):
    def test_all_27_sections_share_one_complete_contract_index(self) -> None:
        prompt_ids = [str(item["id"]) for item in EDITOR_REPORT_PARTS]
        pipeline_ids = [item.part_id for item in SECTION_PIPELINES]
        self.assertEqual(len(prompt_ids), 27)
        self.assertEqual(len(set(prompt_ids)), 27)
        self.assertEqual(prompt_ids, pipeline_ids)
        self.assertEqual(set(prompt_ids), set(EDITOR_PART_REFERENCE_PIPELINES))
        self.assertEqual(set(prompt_ids), set(AUTHORING_SHAPES))
        validate_hwpx_pipeline_contracts()
        validate_report_section_contracts()

    def test_every_section_has_an_independent_prompt_and_adapter(self) -> None:
        prompts = [str(item["prompt"]).strip() for item in EDITOR_REPORT_PARTS]
        adapters = [item.adapter for item in SECTION_PIPELINES]
        self.assertTrue(all(prompts))
        self.assertEqual(len(set(prompts)), 27)
        self.assertEqual(len(set(adapters)), 27)
        for number, part_id in enumerate((item.part_id for item in SECTION_PIPELINES), 1):
            contract = hwpx_authoring_contract(part_id)
            self.assertEqual(contract["number"], number)
            self.assertIn("report_sections.content", contract["source_of_truth"])
            self.assertTrue(contract["authoring_shape"])

    def test_all_prompts_and_hwpx_converters_are_independent_source_files(self) -> None:
        prompt_paths: list[Path] = []
        adapter_modules: list[str] = []
        for part in EDITOR_REPORT_PARTS:
            part_id = str(part["id"])
            prompt_path = prompt_file_for_part(part_id)
            self.assertIsNotNone(prompt_path, part_id)
            assert prompt_path is not None
            self.assertTrue(prompt_path.is_file(), part_id)
            self.assertIn(
                literal_from_prompt_file(prompt_path, "EDITOR_PROMPT"),
                str(part["prompt"]),
                part_id,
            )
            prompt_paths.append(prompt_path.resolve())

            adapter = ADAPTER_BY_PART[part_id]
            self.assertEqual(adapter.normalize_section.__module__, adapter.source_module)
            self.assertEqual(adapter.prepare_section.__module__, adapter.source_module)
            self.assertEqual(adapter.patch_section_xml.__module__, adapter.source_module)
            adapter_modules.append(adapter.source_module)

        self.assertEqual(len(set(prompt_paths)), 27)
        self.assertEqual(len(SECTION_ADAPTERS), 27)
        self.assertEqual(len(set(adapter_modules)), 27)

    def test_reference_routes_use_exact_evidence_slot_titles(self) -> None:
        overview = section_reference_route("project-overview")
        self.assertEqual(overview["criteria"], ["relevance"])
        self.assertEqual(overview["slot_titles"], ["사업개요서 또는 사업요청서 (PCP)"])
        self.assertTrue(overview["uses_uploaded_documents"])

        achievement = section_reference_route("achievement")
        self.assertEqual(achievement["criteria"], ["relevance", "effectiveness"])
        self.assertIn("집행계획서 및 최신 PDM (Project Design Matrix)", achievement["slot_titles"])
        self.assertGreater(len(achievement["slot_titles"]), 1)

    def test_template_owned_sections_do_not_receive_all_uploaded_documents(self) -> None:
        for part_id in ("toc", "notice"):
            route = section_reference_route(part_id)
            self.assertEqual(route["criteria"], [])
            self.assertEqual(route["slot_titles"], [])
            self.assertFalse(route["uses_uploaded_documents"])

    def test_all_narrative_prompts_and_adapters_use_the_shared_outline(self) -> None:
        parts = {str(item["id"]): item for item in EDITOR_REPORT_PARTS}
        for part_id in NARRATIVE_OUTLINE_PART_IDS:
            prompt = str(parts[part_id]["prompt"])
            self.assertIn("[전 서술형 섹션 공통 문단 양식]", prompt, part_id)
            self.assertIn("(핵심어 요약)", prompt, part_id)
            self.assertIn("~함", prompt, part_id)
            self.assertIn("약 360자 이내", prompt, part_id)
            contract = hwpx_authoring_contract(part_id)
            self.assertIn("ㅇ → -", contract["authoring_shape"], part_id)

    def test_narrative_few_shots_label_every_detail_line(self) -> None:
        for part_id in sorted(NARRATIVE_OUTLINE_PART_IDS):
            detail_lines = [
                line.strip() for line in FORMAT_ONLY_DEMOS[part_id].splitlines()
                if line.strip().startswith("-")
            ]
            self.assertTrue(detail_lines, part_id)
            self.assertTrue(
                all(line.startswith("- (") for line in detail_lines),
                f"{part_id}: {detail_lines}",
            )

    def test_summary_uses_parenthesized_block_numbers_and_optional_detail_labels(self) -> None:
        summary_prompt = str(next(item for item in EDITOR_REPORT_PARTS if item["id"] == "summary-ko")["prompt"])
        self.assertIn("(1) 대상사업개요", summary_prompt)
        self.assertIn("선택적으로", summary_prompt)
        self.assertIn("~함", summary_prompt)
        self.assertIn("`-` 앞에는 공백을 두지 않는다", summary_prompt)
        raw_detail_lines = [
            line for line in FORMAT_ONLY_DEMOS["summary-ko"].splitlines()
            if line.lstrip().startswith("-")
        ]
        self.assertTrue(raw_detail_lines)
        self.assertTrue(all(line.startswith("- ") for line in raw_detail_lines))
        detail_lines = [
            line.strip() for line in FORMAT_ONLY_DEMOS["summary-ko"].splitlines()
            if line.strip().startswith("-")
        ]
        self.assertTrue(any(line.startswith("- (") for line in detail_lines))
        self.assertTrue(any(not line.startswith("- (") for line in detail_lines))


if __name__ == "__main__":
    unittest.main()
