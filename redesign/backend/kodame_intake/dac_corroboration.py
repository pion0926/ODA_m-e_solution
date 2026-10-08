"""Discard invalid optional corroboration claims without changing primary evidence."""


def validated_families(value, selected_ids, evidence, question_id):
    accepted, warnings = [], []
    if value is None:
        value = []
    if not isinstance(value, list):
        return [], ['교차검증 출처 그룹 형식 오류: 독립 교차검증에 반영하지 않음']
    for family in value:
        reason = None
        if not isinstance(family, dict):
            reason = '출처 그룹 형식 오류'
        else:
            ids = family.get('evidence_ids')
            if not isinstance(ids, list) or not ids:
                reason = '출처 그룹의 증빙 ID 누락 또는 형식 오류'
            elif any(not isinstance(i, str) or i not in evidence or
                     evidence[i].get('question_id') != question_id or i not in selected_ids
                     for i in ids):
                # Drop the entire claim: retaining a subset could misattribute provenance.
                reason = '선택하지 않았거나 다른 질문·미등록 증빙을 참조한 출처 그룹'
            elif not isinstance(family.get('name'), str) or not family['name'].strip():
                reason = '원출처 기관·데이터 집단 이름 누락'
            elif not isinstance(family.get('provenance'), str) or len(family['provenance'].strip()) < 12:
                reason = '원출처 설명이 불충분한 출처 그룹'
            elif any(not evidence[i].get('source_sha256') for i in ids):
                reason = '원본 식별정보가 없는 출처 그룹'
        if reason:
            warnings.append(reason + ': 독립 교차검증에 반영하지 않음')
        else:
            accepted.append({**family, 'name': family['name'].strip(),
                             'provenance': family['provenance'].strip(),
                             'evidence_ids': list(dict.fromkeys(ids))})
    return accepted, list(dict.fromkeys(warnings))
