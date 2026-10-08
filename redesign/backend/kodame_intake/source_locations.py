"""Coordinates in the exact stored extraction, never guessed PDF geometry."""
import re


def locate(text, quote, *, start=0):
    offset = text.find(quote, start) if quote else -1
    if offset < 0:
        return None
    prefix = text[:offset]
    pages = list(re.finditer(r'\[(?:PDF|OCR) 페이지 (\d+)\]', prefix))
    table = list(re.finditer(r'\[표 (\d+) 행 (\d+)\]', prefix))
    page_start = pages[-1].end() if pages else 0
    in_table = bool(table and table[-1].end() >= text.rfind('\n', 0, offset))
    return {'start': offset, 'end': offset + len(quote),
            'line_start': prefix.count('\n') + 1,
            'line_end': text[:offset + len(quote)].count('\n') + 1,
            'page': int(pages[-1][1]) if pages else None,
            'page_line': text[page_start:offset].count('\n') + 1 if pages else None,
            'table': int(table[-1][1]) if in_table else None,
            'table_row': int(table[-1][2]) if in_table else None,
            'coordinate_system': 'stored_extraction'}


def attach_locations(value, text):
    if isinstance(value, list):
        for item in value:
            attach_locations(item, text)
    elif isinstance(value, dict):
        quote = value.get('evidence_quote') or value.get('quote')
        if isinstance(quote, str) and quote:
            value['source_location'] = locate(text, quote)
        for key, item in list(value.items()):
            if key != 'source_location':
                attach_locations(item, text)
    return value
