"""Resolve a business title from the current plan, separately from AI prose.

Literal grounding alone cannot distinguish a project name from a budget item.
Only front-matter name fields or the cover may establish the report identity.
Read projections preserve the original AI output and its audit history.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from .source_locations import locate

VERSION = 'plan-identity-v1'
NAME_LABEL = re.compile(r'^\s*(?:[•⦁▣ㅇ-]\s*)?사\s*업\s*명\s*(?:\(국문\)|국문)?\s*[:：]?\s*(.*)$')
STOP = re.compile(r'^(?:영\s*문|사업\s*(?:기간|비|목표|내용|규모|대상)|협력국|주관|수행기관|지원기관|기\s*관\s*명|예산|총\s*사업비|단위|산출\s*기초|사용\s*내역|구\s*분|목\s*차|\[PDF|\d{4}[.년])')


def compact(value):
    return re.sub(r'\s+', '', str(value or ''))


def display_title(value):
    title = re.sub(r'\s+', ' ', value).strip()
    # Long English glosses are explanatory, not additional Korean title text.
    if re.search(r'[가-힣]', title):
        title = re.sub(r'\s*\([A-Za-z][A-Za-z ,/-]{8,}\)', '', title)
    if title.startswith('(') and title.count('(') > title.count(')'):
        title = title[1:]
    return re.sub(r'\s+', ' ', title).strip(' 「」“”')


def title_location(text, name, start=0):
    match = re.compile(r'\s+'.join(re.escape(word) for word in name.split())).search(text, start)
    return locate(text, match[0], start=match.start()) if match else None


def plan_title_candidates(text):
    """Read bounded front matter; ignore linked projects and individual tasks."""
    pages = re.split(r'(?=\[PDF 페이지 \d+\])', text)
    front = ''.join(pages[:11])[:20000] if len(pages) > 1 else text[:8000]
    lines = front.splitlines(keepends=True)
    result = []
    offset = 0
    for index, line in enumerate(lines):
        match = NAME_LABEL.match(line.strip())
        preceding = front[max(0, offset-180):offset]
        if match and not re.search(r'연계\s*대상|타\s*사업|과업\s*개요|세부\s*사업', preceding):
            values = [match[1]] if match[1] else []
            for following in lines[index+1:index+9]:
                s = following.strip()
                if not s or re.fullmatch(r'국\s*문', s):
                    continue
                if STOP.match(s):
                    break
                values.append(s)
                if len(' '.join(values)) > 500:
                    break
            name = ' '.join(values).strip()
            if 8 <= len(name) <= 500:
                location = title_location(text, name, start=offset)
                if location:
                    quote = text[location['start']:location['end']]
                    result.append({'value': display_title(name), 'quote': quote,
                                   'source_location': location, 'role': 'project_name_field'})
        offset += len(line)
    if result:
        return result
    # A cover with an explicit plan heading and following title, ending at date.
    first_page = re.split(r'\[PDF 페이지 2\]', text[:4000])[0]
    cover = re.search(r'(?m)^\s*사\s*업\s*계\s*획\s*서\s*\n', first_page)
    if cover:
        block = []
        for line in first_page[cover.end():].splitlines()[:8]:
            if STOP.match(line.strip()):
                break
            if line.strip():
                block.append(line.strip())
        name = ' '.join(block)
        if 8 <= len(name) <= 500 and re.search(r'사업|프로그램|구축|개선|지원', name):
            location = title_location(text, name, start=cover.end())
            if location:
                result.append({'value': display_title(name),
                    'quote': text[location['start']:location['end']],
                    'source_location': location, 'role': 'plan_cover'})
    return result


def resolve_project_identity(text, registered_name=''):
    candidates = plan_title_candidates(text)
    unique = {compact(c['value']): c for c in candidates}
    if len(unique) == 1:
        candidate = next(iter(unique.values()))
        return {'version': VERSION, 'title': candidate['value'], 'source': candidate['role'],
                'quote': candidate['quote'], 'source_location': candidate['source_location']}
    # Never turn an ambiguous or missing name into an invented AI title.
    registered = str(registered_name or '').strip()
    usable = len(registered) >= 8 and not re.search(r'새 ODA|새 프로젝트|테스트|^codex$', registered, re.I)
    return {'version': VERSION, 'title': registered if usable else '사업명 확인 필요',
            'source': 'registered_project' if usable else 'unresolved',
            'reason': 'conflicting_plan_titles' if unique else 'no_formal_plan_title'}


def current_project_identity(conn):
    row = conn.execute("""SELECT id,extracted_path FROM active_intake_documents
        WHERE upload_role='project_plan' AND status='completed'
        ORDER BY queue_position DESC LIMIT 1""").fetchone()
    project = conn.execute("SELECT name FROM projects WHERE id=NULLIF(current_setting('kodame.project_id',true),'')::uuid").fetchone()
    text = ''
    if row and row.get('extracted_path'):
        try:
            text = Path(row['extracted_path']).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            pass
    identity = resolve_project_identity(text, project['name'] if project else '')
    from .project_cover import plan_business_roles
    identity['business_roles'] = plan_business_roles(text)
    if row:
        identity['document_id'] = str(row['id'])
    return identity


def project_title_overview(overview, identity):
    result = deepcopy(overview or {})
    for key, item in identity.get('business_roles', {}).items():
        result[key] = {**item, 'source_refs': ['D001'] if item.get('quote') else [],
                       'document_id': identity.get('document_id')}
    old = result.get('project_name') or {}
    grounded = identity['source'] in {'project_name_field', 'plan_cover'}
    result['project_name'] = {
        'text': identity['title'], 'source_refs': ['D001'] if grounded else [],
        'facts': [{'field': 'project_name', 'value': identity['title'],
                   'quote': identity['quote'], 'source_location': identity['source_location'],
                   'document_id': identity.get('document_id'), 'source_ref': 'D001'}] if grounded else [],
        'identity_resolution': identity, 'original_ai_text': old.get('text', ''),
    }
    return result


def project_title_section(part_id, content, identity):
    """Project only identity slots; preserve scores, reasons and authored prose."""
    import json
    keys = {'cover': ('project_title', ''), 'grade': ('project_label', 'ㅇ 평가대상 사업명 : '),
            'project-overview': ('project_name_ko', '▣ 국문: ')}
    if part_id not in keys or not str(content or '').strip():
        return content
    if part_id == 'cover' and 'business_roles' in identity:
        from .project_cover import cover_slots, cover_text, identity_overview
        overview = identity_overview(identity)
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get('slots'), dict):
            return json.dumps({**parsed, 'slots': cover_slots(overview)}, ensure_ascii=False, indent=2)
        return cover_text(overview)
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get('slots'), dict):
        key, prefix = keys[part_id]
        parsed['slots'][key] = prefix + identity['title']
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    if part_id == 'cover':
        lines = content.splitlines()
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first is not None:
            lines[first] = identity['title']
            return '\n'.join(lines)
    return content
