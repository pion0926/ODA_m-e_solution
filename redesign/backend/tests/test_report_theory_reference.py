import unittest
from pathlib import Path
from unittest.mock import patch

from kodame_intake.theory_visual_prompt import _reference_data_url


class TheoryReferenceTests(unittest.TestCase):
    def test_deployed_reference_is_packaged(self):
        self.assertTrue(_reference_data_url().startswith('data:image/png;base64,iVBOR'))

    def test_missing_reference_has_actionable_error_not_parent_index(self):
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '참고 이미지를 찾을 수 없습니다'):
                _reference_data_url(Path('/missing.png'))

    def test_fallback_finds_reference_in_source_or_container(self):
        self.assertTrue(_reference_data_url(Path('/missing.png')).startswith('data:image/png;base64,iVBOR'))
