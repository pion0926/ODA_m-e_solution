"""Reviewable DAC question scopes derived from intake metadata and original text."""
import hashlib
import json
import re
from pathlib import Path

from fastapi import HTTPException
from .db import connection
from .evaluation_criteria import EVALUATION_CRITERIA
from .dac_rules import RULES
from .project_lifecycle import capture_input_snapshot
from .dac_scope_policy import missing_ranges

VERSION = 'dac-focused-v3'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def text_for(row):
    path = row.get('extracted_path')
    return Path(path).read_text(encoding='utf-8') if path and Path(path).is_file() else ''


def select_ranges(text, question, analysis, *, excluded_ranges=(), max_blocks=3, fallback=True):
    # Navigation only: summaries never become source evidence. Preserve context
    # around matches, including adjacent adverse findings and table headings.
    terms = set(re.findall(r'[\w가-힣]{2,}', question['question'] + ' ' + json.dumps(
        RULES['questions'][question['id']]['checks'], ensure_ascii=False)))
    terms -= {'weight', 'required_evidence', 'criterion', 'min_grade_for_verified', 'id'}
    cid = question['id'].rsplit('-q',1)[0]
    navigation = ' '.join(str(m.get('rationale') or m.get('reason') or '')
                          for m in (analysis.get('evidence_matches') or {}).get('dac_slots', [])
                          if m.get('criterion') == cid)
    terms.update(re.findall(r'[\w가-힣]{3,}', navigation))
    blocks = [(i, min(len(text), i+5000)) for i in range(0, len(text), 4000)]
    matches = (analysis.get('evidence_matches') or {})
    # Intake quotes locate relevant source windows; unrelated PDM/plan or DAC
    # criteria must not outrank the question's own facts merely by volume.
    quotes = [m['evidence_quote'] for m in matches.get('dac_slots', [])
              if m.get('criterion') == cid and m.get('evidence_quote')
              and (not m.get('question_ids') or question['id'] in m['question_ids'])]
    question_facts = [f for f in (analysis.get('registration_facts') or {}).get('facts', [])
                      if question['id'] in f.get('dac_question_ids', [])]
    quotes.extend(f['evidence_quote'] for f in question_facts if f.get('evidence_quote'))
    scored = []
    for start, end in blocks:
        if any(start < old_end and end > old_start for old_start, old_end in excluded_ranges):
            continue
        body = text[start:end].lower()
        score = sum(term.lower() in body for term in terms)
        score += 20 * sum(quote.lower() in body for quote in quotes)
        if score:
            scored.append((score, start, end))
    chosen = sorted(sorted(scored, key=lambda x: (-x[0], x[1]))[:max_blocks], key=lambda x:x[1])
    ranges = []
    for _, start, end in chosen:
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(end, ranges[-1][1])
        else:
            ranges.append([start, end])
    return ranges or ([[0, min(len(text), 5000)]] if text and fallback and not excluded_ranges else [])


def selected_by_history(qid, ident, automatic, previous_plan, previous_ids):
    overrides = previous_plan.get('selection_overrides', {}).get(qid)
    if overrides is not None:
        if ident in overrides.get('excluded', []):
            return False
        return automatic or ident in overrides.get('included', [])
    # Legacy snapshots did not distinguish accepted defaults from user edits.
    # Preserve their exact choices rather than silently removing a manual map.
    if ident in previous_ids and qid in previous_plan.get('mappings', {}):
        return ident in previous_plan['mappings'][qid]
    return automatic


def build_plan(conn=None):
    if conn is None:
        with connection() as current:
            return build_plan(current)
    rows = conn.execute('SELECT * FROM evaluation_intake_documents ORDER BY queue_position').fetchall()
    assignments = conn.execute('SELECT document_id,criterion,slot_id,rationale FROM document_slot_assignments').fetchall()
    previous = conn.execute("SELECT input_snapshot FROM evaluation_runs WHERE input_snapshot ? 'review_plan' ORDER BY started_at DESC LIMIT 1").fetchone()
    previous_plan = (previous['input_snapshot'] or {}).get('review_plan', {}) if previous else {}
    foundation_ids = {str(r['id']) for r in rows if r.get('upload_role') in ('project_plan','pdm')}
    if foundation_ids != {d['id'] for d in previous_plan.get('documents',[]) if d.get('upload_role') in ('project_plan','pdm')}:
        previous_plan = {}
    previous_ids = {d['id'] for d in previous_plan.get('documents',[])}
    documents = []
    texts = {}
    for row in rows:
        analysis = row.get('analysis') or {}
        ident = str(row['id'])
        texts[ident] = text_for(row) if row['status'] == 'completed' else ''
        documents.append({'id':ident, 'file_name':row['original_name'], 'status':row['status'],
            'progress':row.get('progress',0), 'error_message':row.get('error_message'),
            'summary':row.get('summary') or analysis.get('summary',''),
            'artifact':analysis.get('intake_mode') == 'artifact' or row.get('intake_mode') == 'artifact', 'upload_role':row.get('upload_role'),
            'text_digest':digest(texts[ident]), 'sha256':row.get('sha256')})
    indicators = []
    for cid, criterion in EVALUATION_CRITERIA.items():
        for question in criterion['questions']:
            scopes, selected, automatic_ids = {}, [], []
            for row, doc in zip(rows, documents):
                analysis = row.get('analysis') or {}
                links = [a for a in assignments if str(a['document_id']) == doc['id'] and a['criterion'] == cid]
                foundation = doc['upload_role'] in ('project_plan', 'pdm')
                facts = (analysis.get('registration_facts') or {}).get('facts', [])
                question_match = any(question['id'] in f.get('dac_question_ids', []) for f in facts)
                matched = bool(question_match or links or cid in analysis.get('dac_criteria', []))
                automatic = foundation or matched
                if automatic and doc['status'] == 'completed':
                    automatic_ids.append(doc['id'])
                chosen = selected_by_history(question['id'], doc['id'], automatic, previous_plan, previous_ids)
                if chosen and doc['status'] == 'completed':
                    selected.append(doc['id'])
                ranges = select_ranges(texts[doc['id']], question, analysis)
                scopes[doc['id']] = {'ranges':ranges,
                    'unreviewed_ranges': missing_ranges(len(texts[doc['id']]), ranges),
                    'source_characters': len(texts[doc['id']]),
                    'reason': '사업의 계획·목표 대조용 기준 문서' if foundation else
                        ' / '.join(a.get('rationale') or a['slot_id'] for a in links) or
                        ('업로드 시 DAC 기준 매핑' if matched else '사용자가 추가할 수 있는 미매핑 후보'),
                    'limitation': '산출물 내용만으로 사업 제작·배포·성과를 확정하지 않습니다.' if doc['artifact'] else
                        '직접 근거가 부족하면 관련 문서의 미검토 구간을 추가 검토합니다. 필요하면 전체 원문 검토를 직접 선택할 수 있습니다.',
                    'previews':[{'start':s,'end':e,'excerpt':texts[doc['id']][s:min(e,s+600)]} for s,e in ranges]}
            indicators.append({'id':question['id'], 'text':question['question'], 'tier_name':criterion['name'],
                'mov':' / '.join(c['required_evidence'] for c in RULES['questions'][question['id']]['checks']),
                'document_ids':selected,'automatic_document_ids':automatic_ids,'scopes':scopes,
                'selection_overrides':previous_plan.get('selection_overrides', {}).get(question['id'], {}),
                'full_review':any(s.get('mode')=='full' for s in previous_plan.get('scopes',{}).get(question['id'],{}).values())})
    snapshot = capture_input_snapshot(conn)
    active = conn.execute("SELECT id FROM evaluation_runs WHERE status IN ('queued','running') UNION ALL SELECT id FROM pdm_refresh_runs WHERE status IN ('queued','running') LIMIT 1").fetchone()
    from .project_lifecycle import document_blocks_workflow
    pending = sum(document_blocks_workflow(d) for d in documents)
    pdm = conn.execute('SELECT id FROM pdm_models ORDER BY created_at DESC LIMIT 1').fetchone()
    payload = {'version':VERSION,'documents':documents,'indicators':indicators,'input_snapshot':snapshot,
               'pdm_snapshot_id':str(pdm['id']) if pdm else None}
    return {**payload,'revision':digest(payload),'ready':any(d['status']=='completed' for d in documents) and not pending and not active,
        'pending_count':pending,'message':'질문별 검토 문서·구간을 확인하세요. 매핑되지 않은 문서도 추가할 수 있습니다.' if not pending and not active else '문서 처리와 진행 중인 평가가 끝난 뒤 실행할 수 있습니다.'}


def validate_selection(plan, revision, mappings, full_questions):
    if not plan['ready'] or revision != plan['revision']:
        raise HTTPException(409, '자료 또는 상태가 변경되었습니다. 평가 계획을 새로고침해 주세요.')
    qids = {q['id'] for q in plan['indicators']}
    allowed = {d['id'] for d in plan['documents'] if d['status'] == 'completed'}
    if set(mappings) != qids or not set(full_questions) <= qids:
        raise HTTPException(422, '모든 DAC 질문의 문서 선택을 확인해 주세요.')
    scopes, overrides = {}, {}
    for question in plan['indicators']:
        qid = question['id']
        ids = mappings[qid]
        if len(ids) != len(set(ids)) or not set(ids) <= allowed:
            raise HTTPException(422, '현재 프로젝트의 완료된 문서만 연결할 수 있습니다.')
        scopes[qid] = {ident:{**question['scopes'][ident], 'mode':'full' if qid in full_questions else 'focused'} for ident in ids}
        automatic = set(question.get('automatic_document_ids', question.get('document_ids', [])))
        old = question.get('selection_overrides') or {}
        chosen = set(ids)
        overrides[qid] = {
            'included': sorted(((set(old.get('included', [])) & chosen) | (chosen - automatic)) & allowed),
            'excluded': sorted(((set(old.get('excluded', [])) - chosen) | (automatic - chosen)) & allowed),
        }
    if not any(mappings.values()):
        raise HTTPException(422,'평가할 문서를 하나 이상 선택해 주세요.')
    return {'version':VERSION,'revision':revision,'mappings':mappings,'scopes':scopes,'selection_overrides':overrides,
            'input_snapshot':plan['input_snapshot'], 'documents':plan['documents']}


def apply_plan(documents, plan):
    if not plan:
        return documents
    by_id = {d['id']:d for d in plan['documents']}
    selected = []
    for doc in documents:
        scopes = {qid:items[doc['id']] for qid,items in plan['scopes'].items() if doc['id'] in items}
        if not scopes:
            continue
        text = text_for(doc)
        if doc['id'] not in by_id or digest(text) != by_id[doc['id']]['text_digest']:
            raise RuntimeError('검토 계획 작성 이후 원문이 변경되었습니다. 계획을 다시 확인하세요.')
        if doc.get('stored_path') and doc.get('sha256') and hashlib.sha256(Path(doc['stored_path']).read_bytes()).hexdigest() != doc['sha256']:
            raise RuntimeError('DAC 원본 파일 해시가 저장값과 다릅니다.')
        selected.append({**doc,'review_all':False,'question_scopes':scopes,'scope_text':text,
                         'artifact':by_id[doc['id']]['artifact'],
                         'assigned_criteria':sorted({qid.rsplit('-q',1)[0] for qid in scopes})})
    return selected
