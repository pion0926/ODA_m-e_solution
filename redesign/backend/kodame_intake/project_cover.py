"""Cover metadata shared with the project profile; never infer evaluator roles."""
from __future__ import annotations

import re

from .source_locations import locate
from .assessment_context import assessment_date
from .report_policy import REPORT_TITLE


def plan_business_roles(text):
    # Only the plan's front matter may establish the lead institution/person.
    front = ''.join(re.split(r'(?=\[PDF 페이지 \d+\])', text)[:11])[:20000]
    candidates = {'project_manager': [], 'lead_implementer': []}

    def add(key, value, quote):
        value = re.sub(r'\s+', ' ', value).strip(' :：')
        if key == 'project_manager' and re.fullmatch(r'[가-힣\s]{2,12}', value):
            value = re.sub(r'\s+', '', value)
        location = locate(text, quote)
        if value and location and not re.search(r'확인 필요|미정|미확정|예정', value):
            candidates[key].append({'text': value, 'quote': quote, 'source_location': location})

    # Summary table: 주관대학 (사업책임자) /공동대학 기관명(성명).
    for m in re.finditer(r'주관\s*대학\s*\(사업\s*책임자\)\s*(?:/공동대학\s*)?([^\n()]{2,80})\(([가-힣A-Za-z .-]{2,60})\)', front):
        add('lead_implementer', m[1], m[0])
        add('project_manager', m[2], m[0])
    for m in re.finditer(r'국내\s*주관대학\s*\n기\s*관\s*명\s+([^\n]+?)(?=\s+등\s*록|\n|$)', front):
        add('lead_implementer', m[1], m[0])
    for m in re.finditer(r'(?m)^\s*사업\s*(?:\(PM\)\s*)?책임자\s*[:：]\s*([^\n(]{2,60})', front):
        add('project_manager', m[1], m[0])
    for m in re.finditer(r'(?m)^\s*(?:사업\s*수행기관|주관기관)\s*[:：]\s*([^\n]{2,80})', front):
        add('lead_implementer', m[1], m[0])
    result = {}
    for key, values in candidates.items():
        unique = {re.sub(r'\s+', '', v['text']): v for v in values}
        result[key] = next(iter(unique.values())) if len(unique) == 1 else {
            'text': '확인 필요', 'reason': 'conflicting_plan_roles' if unique else 'missing_plan_role'}
    return result


def cover_slots(overview, report_month=None):
    def value(key):
        return str((overview.get(key) or {}).get('text') or '확인 필요').strip()
    # Historical slot IDs are retained for template compatibility. Visible
    # labels describe the plan roles and do not claim an evaluation appointment.
    return {
        'project_title': value('project_name'), 'report_title': REPORT_TITLE,
        'report_date': report_month or assessment_date().strftime('%Y. %m'),
        'evaluation_manager': '사업책임자 ' + value('project_manager'),
        'evaluation_institution': '사업 수행기관 ' + value('lead_implementer'),
    }


def cover_text(overview, report_month=None):
    slots = cover_slots(overview, report_month)
    return '{project_title}\n{report_title}\n\n{report_date}\n\n{evaluation_manager}\n{evaluation_institution}'.format(**slots)


def identity_overview(identity):
    return {'project_name': {'text': identity['title']}, **identity.get('business_roles', {})}
