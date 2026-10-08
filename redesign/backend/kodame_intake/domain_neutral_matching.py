"""Conservative navigation candidates; never establish performance from a name."""
import re


def candidate_match(requirement, name):
    terms = set(re.findall(r'[a-z가-힣]{2,}', requirement.casefold()))
    terms -= {'자료', '문서', '대한', '사업', '결과', '보고서', '통한'}
    hits = sorted(t for t in terms if t in name.casefold())
    if len(hits) < 2:
        return False, 0.0, ''
    return True, min(.8, .55 + .05 * len(hits)), '검증수단·지표의 문서명 후보: ' + ', '.join(hits[:4])
