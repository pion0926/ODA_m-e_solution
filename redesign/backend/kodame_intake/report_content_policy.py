"""Section writing bounds, separate from transport and document layout.

PDM length follows the authoritative source. Requiring 1,500 characters from a
two-indicator PDM caused repeated generation failures and encouraged filler.
Its structural, numerical and source checks remain in force.
"""
QUALITY_TARGETS = {
    "cover": (50, 250), "toc": (100, 1200), "notice": (250, 1400), "grade": (900, 5000),
    "summary-ko": (5200, 9000), "project-background": (1600, 5000), "project-overview": (900, 3500),
    "pdm": (1, 7000), "eval-purpose": (900, 3000), "eval-matrix": (1800, 9000),
    "eval-methods": (1400, 5000), "eval-limitations": (900, 3500), "eval-team": (500, 2200),
    "achievement": (2200, 9000), "criteria-relevance": (1900, 6500), "criteria-coherence": (1900, 6500),
    "criteria-effectiveness": (2400, 8000), "criteria-efficiency": (1900, 6500),
    "criteria-sustainability": (1900, 6500), "criteria-crosscutting": (1200, 4500),
    "criteria-other": (700, 2800), "conclusion": (1600, 5000), "working-factors": (1500, 5200),
    "nonworking-factors": (1500, 5200), "theory": (1600, 5500), "feedback": (1800, 7500),
    "lessons": (1600, 6500),
}


def evidence_targets(part_id, evidence):
    minimum, maximum = QUALITY_TARGETS[part_id]
    length = sum(len(str(e.get('text') or e.get('quote') or e.get('content') or '')) for e in evidence)
    sparse = len(evidence) < 3 or length < 2000
    if sparse and part_id not in ('cover', 'toc', 'notice', 'pdm'):
        return min(minimum, 400), min(maximum, 2200), 'limited'
    return minimum, maximum, 'substantial'
