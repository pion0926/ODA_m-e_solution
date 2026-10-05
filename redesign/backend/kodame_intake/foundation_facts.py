"""Full plan coverage, grounded field facts and explicit unresolved fields."""
from datetime import datetime, timezone
import hashlib
import json

from .ai.prompt_registry import load_prompt
from .openrouter import _request_json, redact_for_external_analysis
from .source_locations import locate
from .structured_output import validate_schema
from .project_identity import plan_title_candidates

FIELDS = ('project_name', 'country', 'location', 'period', 'budget', 'donor',
          'implementer', 'partner', 'background', 'objective', 'beneficiaries',
          'activities', 'outputs', 'outcomes', 'stakeholders', 'timeline', 'evidence_gaps')
VERSION = 'foundation-facts-v2'


def extract_plan_facts(text):
    item = {'type': 'object', 'properties': {
        'field': {'type': 'string', 'enum': list(FIELDS)},
        'value': {'type': 'string'}, 'quote': {'type': 'string'}},
        'required': ['field', 'value', 'quote'], 'additionalProperties': False}
    schema = {'type': 'object', 'properties': {'facts': {'type': 'array', 'items': item}},
              'required': ['facts'], 'additionalProperties': False}
    facts, coverage, rejected = [], [], 0
    titles = plan_title_candidates(text)
    facts.extend({'field': 'project_name', **title} for title in titles)
    for start in range(0, len(text), 16000):
        end = min(len(text), start + 16800)
        chunk, _ = redact_for_external_analysis(text[start:end])
        result, model = _request_json(load_prompt('foundation_overview_facts'),
            json.dumps({'fields': FIELDS, 'text': chunk}, ensure_ascii=False),
            'KODAME Plan Field Facts', response_schema=schema)
        validate_schema(result, schema)
        coverage.append({'start': start, 'end': end, 'model': model})
        for fact in result['facts']:
            # A budget item can be a literal quote and still be the wrong field.
            # Names are read from explicit front-matter fields/cover above.
            if fact['field'] == 'project_name':
                if not any(fact['value'].strip() == title['value'] for title in titles):
                    rejected += 1
                continue
            location = locate(text, fact['quote'], start=start)
            if not location or location['end'] > end or not fact['value'].strip():
                rejected += 1
                continue
            candidate = {**fact, 'source_location': location}
            if candidate not in facts:
                facts.append(candidate)
    return {'version': VERSION, 'source_digest': hashlib.sha256(text.encode()).hexdigest(),
            'extracted_at': datetime.now(timezone.utc).isoformat(), 'facts': facts,
            'coverage': coverage, 'rejected_quotes': rejected,
            'missing_fields': sorted(set(FIELDS) - {f['field'] for f in facts})}
