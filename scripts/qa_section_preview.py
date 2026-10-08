"""Read-only 27-section integration probe, scoped to the existing KNUT project."""
from io import BytesIO
import json
from pathlib import Path
import time
import uuid
import zipfile
import re
import base64
import xml.etree.ElementTree as ET

from kodame_intake.db import pool, tenant_context, connection
from kodame_intake.report_section_preview import build_section_preview

ROOT = Path('/workspace/output/section-preview-20260912')


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    pool.open()
    rows = []
    try:
        with tenant_context(project_id=uuid.UUID('ee8b8006-96eb-4f69-9778-233c42f6f009')):
            with connection() as conn:
                before = conn.execute('SELECT part_id,content,updated_at FROM report_sections ORDER BY section_number').fetchall()
            for item in before:
                started = time.perf_counter()
                try:
                    result = build_section_preview(item['part_id'], item['content'])
                    data = base64.b64decode(result['hwpx_base64'])
                    with zipfile.ZipFile(BytesIO(data)) as z:
                        ET.fromstring(z.read('Contents/section0.xml'))
                        assert len([n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml',n)]) == 1
                        assert len(re.findall(rb'idref="section\d+"',z.read('Contents/content.hpf'))) == 1
                    (ROOT/(item['part_id']+'.hwpx')).write_bytes(data)
                    row = {'part_id':item['part_id'], 'status':'PASS', 'bytes':len(data), 'ms':result['render_ms']}
                except Exception as exc:
                    row = {'part_id':item['part_id'], 'status':'FAIL', 'error':str(exc)}
                print(json.dumps(row, ensure_ascii=False), flush=True)
                rows.append(row)
            with connection() as conn:
                after = conn.execute('SELECT part_id,content,updated_at FROM report_sections ORDER BY section_number').fetchall()
            assert before == after, 'Preview must not modify report content or timestamps'
            (ROOT/'results.json').write_text(json.dumps({'sections':rows,'unchanged':before==after},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        pool.close()
    if any(row['status'] != 'PASS' for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
