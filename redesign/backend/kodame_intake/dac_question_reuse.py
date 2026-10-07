"""Stable question inputs for safe reuse across document additions.

Only completed, revalidated raw judgments may be reused. A new document outside
the question does not change its input; source, scope, model, rubric, project
timing, and the PDM context presented to the assessor still invalidate it.
"""
import hashlib
import json

VERSION = 'dac-question-input-v2'


def source_ref(document_id):
    # Upload-order references shift after exclusions/deletions. References are
    # display/navigation identifiers, so derive them from the document identity.
    return 'D' + hashlib.sha256(str(document_id).encode()).hexdigest()[:16]


def question_documents(corpus, question_id):
    result = []
    for source in corpus:
        reviews = source.get('question_reviews')
        if reviews is not None:
            if question_id not in reviews:
                continue
            review = reviews[question_id]
        else:
            # Compatibility for callers predating explicit scope metadata.
            if not any(e.get('question_id') == question_id for e in source['question_evidence']):
                continue
            review = source['fulltext_review']
        result.append({'ref': source_ref(source['document_id']), 'name': source['file_name'],
                       'summary': source['summary'], 'fulltext_review': review})
    return sorted(result, key=lambda source: source['ref'])


def question_digest(prompt, registry, system_prompt, model, rubric_digest, pdm):
    data = {'version': VERSION, 'prompt': prompt, 'registry': registry,
            'system': system_prompt, 'model': model, 'rubric_digest': rubric_digest,
            # The PDM snapshot UUID/timestamp changes when an equivalent result
            # is saved. Its source identity and semantic model remain inputs.
            'pdm_source': pdm.get('source_document_id'),
            'pdm_source_file': pdm.get('source_file_name'),
            'pdm_performance_status': pdm.get('performance_analysis_status')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                    default=str).encode()).hexdigest()


def matching_checkpoints(checkpoints, question_id, digest):
    candidates = (checkpoints or {}).get(question_id) or []
    if isinstance(candidates, dict):
        candidates = [candidates]
    return [candidate for candidate in candidates
            if isinstance(candidate, dict) and candidate.get('digest') == digest
            and isinstance(candidate.get('raw'), dict)]
