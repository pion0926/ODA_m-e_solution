"""Conservative detection of suspicious negatives, independent of AI rationale."""
import re


def suspicious_negatives(indicators, text, payload, facts=()):
    found = {o.get('indicator_id') for o in payload.get('observations', [])}
    suspects = []
    for indicator in indicators:
        if indicator['id'] in found:
            continue
        registered = any(indicator['id'] in f.get('pdm_indicator_ids', []) and
                         f.get('evidence_quote') and f['evidence_quote'] in text for f in facts)
        terms = set(re.findall(r'[a-zA-Z가-힣]{2,}', indicator.get('indicator', '')))
        terms -= {'증가', '감소', '지표', '목표', '성과', '대한', '통한'}
        numeric_context = any(re.search(r'\d', line) and any(t.lower() in line.lower() for t in terms)
                              for line in text.splitlines())
        if registered or numeric_context:
            suspects.append(indicator)
    return suspects
