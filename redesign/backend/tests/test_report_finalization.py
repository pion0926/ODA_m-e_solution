import hashlib
import unittest
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from kodame_intake.rhwp_renderer import analyze_rhwp, finalize_toc_with_rhwp
from kodame_intake.rhwp_geometry import GEOMETRY_VERSION
from kodame_intake.report_rhwp_verification import DESTINATIONS, rhwp_page_map
from kodame_intake.report_generator import GENERATION_ORDER, _deterministic_safe_section, _normalize_project_phase_labels
from kodame_intake.report_policy import REPORT_TITLE
from kodame_intake.theory_visual import PALETTE, theory_visual_input_digest
from kodame_intake import theory_artifact_store as cache
from kodame_intake.db import tenant_context


def rendered(data, shift=0):
    texts = ["표지", "목차"] + ["빈 쪽"] * shift + [title for _, title in DESTINATIONS]
    return {"page_count": len(texts), "page_texts": [
        {"page_number": index+1, "text": value, "geometry": {"version": GEOMETRY_VERSION, "ok": True}}
        for index, value in enumerate(texts)],
        "source_sha256": hashlib.sha256(data).hexdigest()}


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.template = next((Path(__file__).resolve().parents[3] / "samples").glob("*placeholder.hwpx")).read_bytes()

    def test_toc_last_generation_and_preserved_fixed_title(self):
        self.assertEqual(len(set(GENERATION_ORDER)), 27)
        self.assertEqual(GENERATION_ORDER[-1], "toc")
        self.assertIn(REPORT_TITLE, _deterministic_safe_section("cover", {"project_name": {"text": "시험사업"}}, {}))
        self.assertIn(REPORT_TITLE, _normalize_project_phase_labels(REPORT_TITLE, {"project_status": "ongoing"}))

    def test_repagination_after_patch_is_required_and_exact_bytes_verified(self):
        calls = []
        def render(data):
            calls.append(data)
            return rendered(data, 0 if len(calls) == 1 else 1)
        final, meta = finalize_toc_with_rhwp(self.template, render=render)
        self.assertEqual(len(calls), 3)
        self.assertEqual(meta["source_sha256"], hashlib.sha256(final).hexdigest())
        self.assertEqual(meta["page_map"]["summary_ko_page"], "6")
        self.assertTrue(meta["visible_validation"]["ok"])

    def test_nonconverging_pagination_never_claims_complete(self):
        calls = []
        def render(data):
            calls.append(data)
            return rendered(data, len(calls) % 2)
        with self.assertRaisesRegex(RuntimeError, "안정화"):
            finalize_toc_with_rhwp(self.template, render=render, max_passes=4)

    def test_missing_out_of_order_and_invalid_pages_rejected(self):
        for payload in ({}, {"page_count": 201, "page_texts": []}, {"page_count": 3, "page_texts": [{"page_number": i, "text": ""} for i in (1, 3, 2)]}):
            with self.assertRaises(ValueError):
                rhwp_page_map(payload)

    def test_correct_toc_never_certifies_clipped_or_unchecked_pages(self):
        for geometry in ({}, {'version': GEOMETRY_VERSION, 'ok': False,
                              'errors': [{'kind': 'text_outside_page'}]}):
            with self.subTest(geometry=geometry):
                def render(data):
                    value = rendered(data)
                    value['page_texts'][4]['geometry'] = geometry
                    return value
                with self.assertRaisesRegex(RuntimeError, '잘린 보고서'):
                    finalize_toc_with_rhwp(self.template, render=render)

    def test_empty_rhwp_input_rejected_before_browser_start(self):
        with self.assertRaises(ValueError):
            analyze_rhwp(b"")

    def test_visual_cache_changes_with_sources_evaluation_and_body(self):
        project = {"project": {"title": "농촌 식수사업"}}
        body = {"theory": "기반시설 구축을 통한 급수 접근성 개선"}
        baseline = {"document_digest": "one", "evaluation_run_id": "e1"}
        digest = theory_visual_input_digest(project, body, baseline)
        self.assertEqual(digest, theory_visual_input_digest(project, body, baseline))
        for changed in ({"document_digest": "two", "evaluation_run_id": "e1"}, {"document_digest": "one", "evaluation_run_id": "e2"}):
            self.assertNotEqual(digest, theory_visual_input_digest(project, body, changed))
        self.assertNotEqual(digest, theory_visual_input_digest(project, {"theory": "새 근거"}, baseline))

    def test_dark_diagram_text_has_high_contrast(self):
        def luminance(color):
            rgb = [int(color[i:i+2], 16)/255 for i in (0, 2, 4)]
            rgb = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(c*w for c,w in zip(rgb, (.2126,.7152,.0722)))
        for key in ("ink", "muted", "working", "nonworking"):
            self.assertGreaterEqual(1.05/(luminance(PALETTE[key])+.05), 7, key)

    def test_artifact_cache_is_project_scoped_and_corruption_safe(self):
        digest = "a" * 64
        first, second = uuid.uuid4(), uuid.uuid4()
        artifacts = {"pptx": b"pptx", "png": b"png", "plan": {"title": "현재 사업"}}
        with tempfile.TemporaryDirectory() as directory, patch.object(cache, "CACHE_ROOT", Path(directory)):
            with tenant_context(first):
                cache.save_theory_artifact(digest, artifacts)
                self.assertEqual(cache.load_theory_artifact(digest)["png"], b"png")
            with tenant_context(second):
                self.assertIsNone(cache.load_theory_artifact(digest))
            with tenant_context(first):
                (Path(directory) / str(first) / digest / "theory.png").write_bytes(b"damaged")
                self.assertIsNone(cache.load_theory_artifact(digest))


if __name__ == "__main__":
    unittest.main()
