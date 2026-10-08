from __future__ import annotations

from backend.oda_me.hwpx.patchers import patch_hwpx_review_section_slots_xml

from ..section_adapter import (
    CommonNormalizer,
    SectionHwpxAdapter,
    SectionPatchResult,
    SectionPipelineSpec,
)


def normalize_with_contract(
    part_id: str,
    max_chars: int,
    value: str,
    normalizer: CommonNormalizer,
) -> tuple[str, dict]:
    return normalizer(part_id, value, max_chars)


def keep_prepared(
    part_id: str,
    _context: dict,
    _raw_sections: dict[str, str],
    prepared_sections: dict[str, str],
    _evaluations: list[dict],
) -> str:
    return prepared_sections.get(part_id, "")


def patch_review_section(
    section_number: int,
    xml: str,
    context: dict,
    prepared_sections: dict[str, str],
) -> SectionPatchResult:
    patched, changed = patch_hwpx_review_section_slots_xml(
        xml,
        section_number,
        context,
        prepared_sections,
    )
    return SectionPatchResult(patched, changed, {})


def build_adapter(
    *,
    number: int,
    part_id: str,
    title: str,
    hwpx_path: str,
    mode: str,
    adapter_id: str,
    max_chars: int,
    layout_rule: str,
    authoring_shape: str,
    normalize_section,
    prepare_section,
    patch_section_xml,
    source_module: str,
) -> SectionHwpxAdapter:
    return SectionHwpxAdapter(
        spec=SectionPipelineSpec(
            number,
            part_id,
            title,
            hwpx_path,
            mode,
            adapter_id,
            max_chars,
            layout_rule,
        ),
        authoring_shape=authoring_shape,
        normalize_section=normalize_section,
        prepare_section=prepare_section,
        patch_section_xml=patch_section_xml,
        source_module=source_module,
    )
