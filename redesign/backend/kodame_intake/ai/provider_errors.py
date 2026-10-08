"""Normalize HTTP and in-body provider errors without retaining credentials."""
import json
import re


def error_info(http_status, body):
    error = body.get('error') if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {'message': str(error or '')}
    try:
        code = int(error.get('code') or http_status)
    except (ValueError, TypeError):
        code = http_status if http_status >= 400 else 500
    if http_status >= 400:
        code = http_status
    elif error.get('message') and code < 400:
        code = 500
    metadata = error.get('metadata') or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    details = [str(error.get('message') or '')]
    raw = metadata.get('raw')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = {'message': raw}
    if isinstance(raw, dict):
        upstream = raw.get('error') or raw
        if isinstance(upstream, dict):
            details.append(str(upstream.get('message') or ''))
    detail = ' '.join(dict.fromkeys(d for d in details if d)).strip()
    # Error metadata is untrusted and can echo a key or authorization header.
    detail = re.sub(r'(?i)bearer\s+\S+', 'Bearer [redacted]', detail)
    detail = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', detail)
    detail = re.sub(r'(?i)((?:api[_-]?key|authorization|token)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', detail)
    detail = ''.join(c if c >= ' ' else ' ' for c in detail)[:1500]
    return code, detail or '공급자가 상세 원인을 제공하지 않았습니다.', metadata


def is_context_limit(detail):
    return any(term in detail.lower() for term in (
        'context length', 'context_length', 'maximum context', 'too many tokens',
        'input too long', 'context window', 'exceeds the model', 'exceed context'))


def is_schema_rejection(detail):
    detail = detail.lower()
    return ('no endpoints' in detail and 'parameter' in detail) or (
        any(s in detail for s in ('json_schema', 'response_format', 'structured output'))
        and any(s in detail for s in ('not supported', 'unsupported', 'does not support'))) or any(
            s in detail for s in ('compiled grammar is too large', 'schema is too complex', 'schema too complex'))
