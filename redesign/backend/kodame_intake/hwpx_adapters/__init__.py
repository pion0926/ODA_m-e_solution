"""Composable semantic adapters used before deterministic HWPX rendering."""

from .registry import (
    ADAPTER_BY_NUMBER,
    ADAPTER_BY_PART,
    AUTHORING_SHAPES,
    SECTION_ADAPTERS,
    SECTION_PIPELINES,
    SPEC_BY_PART,
    AdapterComposition,
    apply_section_adapter_xml,
    compose_registered_adapter,
    hwpx_authoring_contract,
    validate_section_adapters,
)

__all__ = [
    "ADAPTER_BY_NUMBER",
    "ADAPTER_BY_PART",
    "AUTHORING_SHAPES",
    "SECTION_ADAPTERS",
    "SECTION_PIPELINES",
    "SPEC_BY_PART",
    "AdapterComposition",
    "apply_section_adapter_xml",
    "compose_registered_adapter",
    "hwpx_authoring_contract",
    "validate_section_adapters",
]
