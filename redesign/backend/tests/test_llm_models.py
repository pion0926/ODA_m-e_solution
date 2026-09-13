from __future__ import annotations

import unittest

from kodame_intake.llm_models import (
    ALLOWED_MODEL_IDS,
    DEFAULT_MODEL,
    current_llm_model,
    llm_model_context,
    validate_model,
)


class LlmModelSettingsTests(unittest.TestCase):
    def test_supported_models_are_pinned_concrete_openrouter_ids(self) -> None:
        self.assertIn("google/gemini-3.5-flash-lite", ALLOWED_MODEL_IDS)
        self.assertIn("anthropic/claude-opus-4.8", ALLOWED_MODEL_IDS)

    def test_unsupported_model_cannot_be_saved(self) -> None:
        with self.assertRaises(ValueError):
            validate_model("vendor/unreviewed-model")

    def test_job_model_is_fixed_for_the_context_and_then_restored(self) -> None:
        before = current_llm_model()
        with llm_model_context("anthropic/claude-opus-4.8"):
            self.assertEqual(current_llm_model(), "anthropic/claude-opus-4.8")
        self.assertEqual(current_llm_model(), before)
        self.assertEqual(before, DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()

