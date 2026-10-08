"""Evidence-purpose mappings, separate from topic links and measured achievements."""
VERSION = 4
EVIDENCE_KINDS = {'direct_record', 'calculation_input', 'qualitative_evidence'}
RESULT_RELATIONS = {'reported_result', 'observed_result', 'calculation_component', 'measured_change'}


def qualifies(item):
    return (item.get('evidence_kind') in EVIDENCE_KINDS
            and item.get('measurement_relation') in RESULT_RELATIONS
            and item.get('subject_match') is True
            and item.get('activity_match') is True
            and item.get('scope_match') is True
            and bool(str(item.get('proves', '')).strip())
            and bool(str(item.get('evidence_quote', '')).strip())
            and float(item.get('confidence') or 0) >= .75)


def manual_overrides(analysis, source_id):
    override = analysis.get('pdm_mapping_overrides') or {}
    if override.get('source_document_id') != str(source_id):
        return set(), set()
    if override.get('version', 0) >= 3:
        return set(override.get('included', [])), set(override.get('excluded', []))
    # Old UI saved every accepted default as "manual". Only additions absent
    # from the original AI proposal can be identified as deliberate additions.
    original = analysis.get('evidence_matches') or {}
    automatic = {i['indicator_id'] for i in original.get('pdm', [])}
    return set(override.get('included', [])) - automatic, set(override.get('excluded', []))


def decision(document, indicator_id, source_id):
    analysis = document.get('analysis') or {}
    added, removed = manual_overrides(analysis, source_id)
    if indicator_id in removed:
        return None
    if indicator_id in added:
        return {'indicator_id': indicator_id, 'confidence': 1.0,
                'rationale': '사용자가 직접 추가한 증빙 연결', 'evidence_kind': 'manual',
                'proves': '사용자가 지표 증빙으로 직접 지정', 'mapping_origin': 'manual'}
    saved = analysis.get('evidence_matches') or {}
    if saved.get('version') != VERSION or str((saved.get('sources', {}).get('pdm') or {}).get('id')) != str(source_id):
        return None
    return next(({**i, 'mapping_origin': 'automatic'} for i in saved.get('pdm', [])
                 if i.get('indicator_id') == indicator_id and qualifies(i)), None)
