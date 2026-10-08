"""Typed contracts for deterministic HWPX section adapters."""

from .contracts import AdapterContract, AdapterContractError, SlotContract
from .summary_ko import (
    SUMMARY_KO_ADAPTER,
    SUMMARY_KO_SLOT_KEYS,
    assert_summary_ko_payload,
    normalize_summary_ko_value,
    parse_summary_ko_section,
    validate_summary_ko_manifest,
)

__all__ = [
    "AdapterContract",
    "AdapterContractError",
    "SlotContract",
    "SUMMARY_KO_ADAPTER",
    "SUMMARY_KO_SLOT_KEYS",
    "assert_summary_ko_payload",
    "normalize_summary_ko_value",
    "parse_summary_ko_section",
    "validate_summary_ko_manifest",
]
