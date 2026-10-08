import re
import unittest
from backend.oda_me.hwpx.patchers import find_hwpx_tag_spans, get_hwpx_xml_scope_text
from kodame_intake.hwpx_layout.project_overview import _split_overview_at_merged_groups


class OverviewPaginationTests(unittest.TestCase):
    def table(self, height=16000):
        rows = []
        for i in range(5):
            merged = f'<hp:tc><hp:cellAddr colAddr="0" rowAddr="{i}"/><hp:cellSpan colSpan="1" rowSpan="2"/><hp:cellSz width="2000" height="{height*2}"/></hp:tc>' if i in (1, 3) else ''
            rows.append(f'<hp:tr>{merged}<hp:tc><hp:cellAddr colAddr="1" rowAddr="{i}"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="20000" height="{1000 if i == 0 else height}"/><hp:p><hp:run><hp:t>cell{i}</hp:t></hp:run></hp:p></hp:tc></hp:tr>')
        return '<hp:tbl id="100" rowCnt="5"><hp:sz width="22000" height="65000"/>' + ''.join(rows) + '</hp:tbl>'

    def test_split_preserves_groups_and_last_cell(self):
        output = _split_overview_at_merged_groups(self.table())
        tables = [output[s:e] for s, e in find_hwpx_tag_spans(output, 'hp:tbl')]
        self.assertEqual(len(tables), 2)
        self.assertIn('cell4', get_hwpx_xml_scope_text(tables[1]))
        self.assertNotIn('cell3', get_hwpx_xml_scope_text(tables[0]))
        for table in tables:
            self.assertIn('rowCnt="3"', table)
            self.assertEqual(_split_overview_at_merged_groups(table), table)
            self.assertLessEqual(int(re.search(r'<hp:sz[^>]*height="(\d+)"', table).group(1)), 60000)

    def test_one_group_cannot_be_silently_cropped(self):
        with self.assertRaises(ValueError):
            _split_overview_at_merged_groups(self.table(40000))
