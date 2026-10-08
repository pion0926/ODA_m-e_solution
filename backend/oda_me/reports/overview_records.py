"""Recover the legacy overview's twelve cells without changing reviewed facts.

Only explicitly delimited, complete records are accepted. Ordinary slashes in
names, dates and budget descriptions are not cell boundaries.
"""
from __future__ import annotations

import re

from .context import SECTION7_PROJECT_OVERVIEW_SLOT_KEYS


def legacy_overview_slots(content: str) -> dict[str, str] | None:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) == 12 and all(line.startswith(("▣", "󰁯")) for line in lines):
        return dict(zip(SECTION7_PROJECT_OVERVIEW_SLOT_KEYS, lines))
    tokens = [part.strip() for part in re.split(r"\s*/\s*(?=[▣󰁯▪])", content.strip())]
    if len(tokens) < 16 or not re.match(r"▣\s*국문\s*:", tokens[0]):
        return None
    if not re.match(r"▣\s*영문\s*:", tokens[1]):
        return None
    period = next((i for i, token in enumerate(tokens) if re.match(r"▣\s*(구분|기간)\s*:", token)), -1)
    review = next((i for i, token in enumerate(tokens) if token.startswith("󰁯")), -1)
    budgets = [i for i, token in enumerate(tokens) if re.match(r"▣\s*소요예산\s*:", token)]
    if period != 3 or review < 7 or len(budgets) != 4 or budgets[0] <= review:
        return None
    end_period = period
    while end_period < review and re.match(r"▣\s*(구분|기간|총\s*사업예산)\s*:", tokens[end_period]):
        end_period += 1
    if end_period + 1 >= review:
        return None
    if not all(token.startswith("󰁯") for token in tokens[review:budgets[0]]):
        return None
    # Each contribution has one budget marker followed by one or more details.
    # A separate final ▣ entry is the partner contribution, never a fifth budget.
    if not tokens[-1].startswith("▣") or budgets[-1] >= len(tokens) - 2:
        return None
    groups = [tokens[start:end] for start, end in zip(budgets, budgets[1:] + [len(tokens) - 1])]
    if any(len(group) < 2 or not all(token.startswith("▪") for token in group[1:]) for group in groups):
        return None
    values = [
        tokens[0], tokens[1], tokens[2], " / ".join(tokens[period:end_period]),
        tokens[end_period], " / ".join(tokens[end_period + 1:review]),
        " / ".join(tokens[review:budgets[0]]),
        *(" / ".join(group) for group in groups), tokens[-1],
    ]
    return dict(zip(SECTION7_PROJECT_OVERVIEW_SLOT_KEYS, values))
