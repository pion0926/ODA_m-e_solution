import unittest
import zipfile
import re
from io import BytesIO
from pathlib import Path
import xml.etree.ElementTree as ET

from kodame_intake.hwpx_layout.toc_columns import fixed_toc_columns
from kodame_intake.hwpx_layout.toc import patch_toc_page_numbers
from backend.oda_me.hwpx.patchers import TOC_SECTION2_LABELS, _toc_labeled_numeric_target


class TocColumnsTests(unittest.TestCase):
    def test_number_updates_preserve_fixed_geometry(self):
        template=next((Path(__file__).resolve().parents[3]/'samples').glob('*placeholder.hwpx'))
        pages={k:str(6 if i==0 else 13+i) for i,k in enumerate(TOC_SECTION2_LABELS)}
        first,_=patch_toc_page_numbers(template.read_bytes(),pages)
        self.assertEqual(fixed_toc_columns(first),(first,0))
        changed={k:str(99 if i==0 else 7) for i,k in enumerate(TOC_SECTION2_LABELS)}
        second,_=patch_toc_page_numbers(first,changed)
        with zipfile.ZipFile(BytesIO(first)) as a,zipfile.ZipFile(BytesIO(second)) as b:
            s1=a.read('Contents/section1.xml').decode();s2=b.read('Contents/section1.xml').decode()
            self.assertEqual(a.read('Contents/header.xml'),b.read('Contents/header.xml'))
            self.assertEqual(re.findall(r'<hp:cellSz[^>]*/>',s1),re.findall(r'<hp:cellSz[^>]*/>',s2))
            self.assertEqual(s2.count('name="toc_number_'),20)
            for _,_,p in [(t[0],t[1],t[2]) for label in TOC_SECTION2_LABELS.values() if (t:=_toc_labeled_numeric_target(s2,label))]:
                self.assertNotIn('<hp:tab ',p)
            for k,label in TOC_SECTION2_LABELS.items():
                target=_toc_labeled_numeric_target(s2,label)
                self.assertIsNotNone(target)
                self.assertEqual(target[3][2],changed[k])
            ns={'p':'http://www.hancom.co.kr/hwpml/2011/paragraph'}
            root=ET.fromstring(s2)
            for table in root.findall('.//p:tbl',ns):
                cells=table.findall('./p:tr/p:tc',ns)
                if not any(c.get('name','').startswith('toc_number_') for c in cells):continue
                self.assertEqual(len(cells),3)
                self.assertEqual(sum(int(c.find('p:cellSz',ns).get('width')) for c in cells),int(table.find('p:sz',ns).get('width')))
