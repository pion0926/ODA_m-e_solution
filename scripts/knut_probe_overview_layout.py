"""Read-only source probe of overview table anchoring; writes diagnostic copies only."""
from pathlib import Path
from io import BytesIO
import json
import re
import zipfile

from backend.oda_me.hwpx.patchers import find_hwpx_table_span_by_text
from kodame_intake.hwpx_layout.rendering import analyze_hwpx


root = Path('/workspace/output/knut-e2e-20260911/service-layout-diagnostic')
source = root.joinpath('candidate.hwpx').read_bytes()
with zipfile.ZipFile(BytesIO(source)) as original:
    xml = original.read('Contents/section3.xml').decode('utf-8')
    start, end, table = find_hwpx_table_span_by_text(xml, ['내용', '사업개요', '사업명(국문)'], 20)
    table = re.sub(r'(\btreatAsChar=")0', r'\g<1>1', table, count=1)
    updated = xml[:start] + table + xml[end:]
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as target:
        for info in original.infolist():
            target.writestr(info, updated.encode('utf-8') if info.filename == 'Contents/section3.xml' else original.read(info.filename))
data = output.getvalue()
root.joinpath('overview-inline-probe.hwpx').write_bytes(data)
analysis = analyze_hwpx(data, 'http://kodame-kordoc:8200', stage='overview-inline-probe')
root.joinpath('overview-inline-probe-analysis.json').write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pages': analysis.get('render', {}).get('page_count'), 'overlaps': analysis.get('render', {}).get('line_overlap_risks')}, ensure_ascii=False))
