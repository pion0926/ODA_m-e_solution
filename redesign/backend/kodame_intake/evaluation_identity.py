"""Read evaluator roles only from an explicit evaluation commissioning record."""
import re
from pathlib import Path


def evaluator_identity(documents):
    result = {'evaluation_manager': '', 'evaluation_institution': '', 'evaluation_identity_source': ''}
    for document in documents:
        name = str(document.get('original_name') or '')
        # A historical self-evaluation's submitter/project manager is not the
        # evaluator of this report. Require a commissioning/roster document.
        if '자체평가' in name or not re.search(
            r'(?:종료평가|최종평가|외부평가).*(?:수행계획|실시계획|평가팀|평가자|위촉|용역계약)', name
        ):
            continue
        try:
            source = Path(str(document.get('extracted_path') or '')).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        values = {}
        for field, label in (('evaluation_manager', '평가\\s*책임자'), ('evaluation_institution', '평가\\s*수행기관')):
            match = re.search(r'(?m)^\s*' + label + r'\s*[:：]\s*([^\n|]{1,100})', source)
            if match and not re.search(r'확인\s*필요|미정|미확정|예정', match.group(1)):
                values[field] = match.group(1).strip()
        if values:
            return {**result, **values, 'evaluation_identity_source': name}
    return result
