"""Bounded validation feedback for evidence-only report recovery responses."""
from __future__ import annotations


def repair_recovery_response(content, validate, repair, finalize, *, attempts=2):
    """Never waive a contract or invent filler; return remaining issues openly.

    The primary writer has its own QA cycle. A fresh recovery response can
    introduce different defects, so it needs feedback on its actual output.
    Callers keep the previous saved section until these checks all pass.
    """
    issues = validate(content)
    used = 0
    while issues and used < attempts:
        candidate = repair(content, issues)
        used += 1
        if not isinstance(candidate, str) or not candidate.strip():
            break
        content = finalize(candidate)
        issues = validate(content)
    return content, issues, used
