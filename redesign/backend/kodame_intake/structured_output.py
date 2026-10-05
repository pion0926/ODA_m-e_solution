"""Provider-neutral output contract. Never repair or invent missing evidence."""
import json
import re

from jsonschema import Draft202012Validator

OUTPUT_RULES = r'''
[OUTPUT CONTRACT — applies to GPT, Gemini and Claude alike]
Return exactly one complete JSON object conforming to the supplied JSON Schema.
No Markdown fences, commentary, XML, comments, ellipses, or text before/after JSON.
Use double-quoted keys/strings; escape embedded quotes, backslashes and newlines
(\" / \\ / \n). No trailing commas, duplicate keys, NaN or Infinity.
Include every required field, with its exact name and type. No extra fields.
Use [] for an empty array. Do not substitute null, a string or an object for an array.
Numbers and booleans must be JSON numbers and true/false, not quoted strings.
Copy reference IDs exactly from the allowed lists. Document IDs, evidence IDs,
question IDs and PDM indicator IDs are different namespaces; never interchange them.
Missing evidence must remain unverified; never invent a fact, reference or score
to satisfy the schema. Keep explanations concise so the entire object fits.
Complete and close every array/object before ending the response.
'''


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_object(content):
    if isinstance(content, list):
        if any(not isinstance(p, dict) or p.get('type') not in ('text', 'output_text')
               or not isinstance(p.get('text'), str) for p in content):
            raise ValueError('응답에 지원되지 않는 콘텐츠 블록이 있습니다.')
        content = ''.join(p['text'] for p in content)
    if not isinstance(content, str) or not content.strip():
        raise ValueError('AI 응답 본문이 비어 있습니다.')
    value = content.lstrip('\ufeff').strip()
    # Unwrap a complete fence only. Do not splice truncated JSON or alter facts.
    if value.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', value, re.I)
        if match:
            value = match[1]
    def invalid_constant(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    parsed = json.loads(value, object_pairs_hook=_unique_object, parse_constant=invalid_constant)
    if not isinstance(parsed, dict):
        raise ValueError('AI 응답 최상위 값은 JSON 객체여야 합니다.')
    json.dumps(parsed, allow_nan=False)  # Also rejects overflowing numeric literals such as 1e999.
    def check_unicode(item):
        if isinstance(item, str):
            if '\x00' in item or any(0xD800 <= ord(c) <= 0xDFFF for c in item):
                raise ValueError('Unsupported Unicode code point in JSON string')
        elif isinstance(item, dict):
            for key, val in item.items():
                check_unicode(key)
                check_unicode(val)
        elif isinstance(item, list):
            for val in item:
                check_unicode(val)
    check_unicode(parsed)
    return parsed


def validate_schema(value, schema):
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error:
        # Log paths/types, never a full document or raw provider output.
        path = '.'.join(str(p) for p in error.absolute_path) or '$'
        raise ValueError(f'JSON schema mismatch at {path}: {error.validator}')
