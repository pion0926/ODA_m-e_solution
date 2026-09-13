import unittest
from kodame_intake.hwpx_layout.cell_wrapping import normalize_table_cell_wrapping


class CellWrappingTests(unittest.TestCase):
    def test_only_table_cells_change_and_text_is_preserved(self):
        source = '<hp:subList lineWrap="SQUEEZE"/><hp:tc><hp:subList lineWrap="SQUEEZE"><hp:p>근거를 충분히 작성함</hp:p></hp:subList></hp:tc>'
        fixed, count = normalize_table_cell_wrapping(source)
        self.assertEqual(count, 1)
        self.assertTrue(fixed.startswith('<hp:subList lineWrap="SQUEEZE"/>'))
        self.assertIn('<hp:tc><hp:subList lineWrap="BREAK">', fixed)
        self.assertIn('근거를 충분히 작성함', fixed)
        self.assertEqual(normalize_table_cell_wrapping(fixed), (fixed, 0))

    def test_missing_or_keep_mode_are_normalized(self):
        for attrs in ('', ' lineWrap="KEEP"'):
            fixed, count = normalize_table_cell_wrapping(f'<hp:tc><hp:subList{attrs}></hp:subList></hp:tc>')
            self.assertEqual(count, 1)
            self.assertIn('lineWrap="BREAK"', fixed)
