from __future__ import annotations

from ._shared import build_adapter, keep_prepared, normalize_with_contract, patch_review_section

PART_ID = "toc"
MAX_CHARS = 1200


def normalize(value, normalizer):
    return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)


def prepare(context, raw_sections, prepared_sections, evaluations):
    return keep_prepared(PART_ID, context, raw_sections, prepared_sections, evaluations)


def patch_xml(xml, context, prepared_sections):
    from ...hwpx_layout.toc import (
        clean_toc_annotations_xml,
        normalize_toc_page_number_spacing_xml,
    )

    result = patch_review_section(2, xml, context, prepared_sections)
    normalized, spacing_changed = normalize_toc_page_number_spacing_xml(
        clean_toc_annotations_xml(result.xml)
    )
    return type(result)(
        normalized,
        result.changed + spacing_changed,
        {**result.metrics, "page_number_spacing_normalized": spacing_changed},
    )


ADAPTER = build_adapter(
    number=2, part_id=PART_ID, title="목차", hwpx_path="Contents/section1.xml",
    mode="toc", adapter_id="toc_page_numbers", max_chars=MAX_CHARS,
    layout_rule="원본 목차 순서 보존, 최종 쪽수만 후처리",
    authoring_shape="새 목차를 만들지 않는다. 원본 목차의 제목 순서를 보존하고 쪽수 계산에 필요한 내용만 유지한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml,
    source_module=__name__,
)
