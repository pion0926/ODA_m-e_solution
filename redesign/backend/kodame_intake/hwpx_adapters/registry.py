from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from report_outline import NARRATIVE_OUTLINE_PART_IDS, NARRATIVE_OUTLINE_PROMPT

from .summary_ko import compose_summary_ko
from .section_adapter import SectionHwpxAdapter, SectionPatchResult
from .sections.section01_cover import ADAPTER as SECTION01
from .sections.section02_toc import ADAPTER as SECTION02
from .sections.section03_notice import ADAPTER as SECTION03
from .sections.section04_grade import ADAPTER as SECTION04
from .sections.section05_summary_ko import ADAPTER as SECTION05
from .sections.section06_project_background import ADAPTER as SECTION06
from .sections.section07_project_overview import ADAPTER as SECTION07
from .sections.section08_pdm import ADAPTER as SECTION08
from .sections.section09_eval_purpose import ADAPTER as SECTION09
from .sections.section10_eval_matrix import ADAPTER as SECTION10
from .sections.section11_eval_methods import ADAPTER as SECTION11
from .sections.section12_eval_limitations import ADAPTER as SECTION12
from .sections.section13_eval_team import ADAPTER as SECTION13
from .sections.section14_achievement import ADAPTER as SECTION14
from .sections.section15_criteria_relevance import ADAPTER as SECTION15
from .sections.section16_criteria_coherence import ADAPTER as SECTION16
from .sections.section17_criteria_effectiveness import ADAPTER as SECTION17
from .sections.section18_criteria_efficiency import ADAPTER as SECTION18
from .sections.section19_criteria_sustainability import ADAPTER as SECTION19
from .sections.section20_criteria_crosscutting import ADAPTER as SECTION20
from .sections.section21_criteria_other import ADAPTER as SECTION21
from .sections.section22_conclusion import ADAPTER as SECTION22
from .sections.section23_working_factors import ADAPTER as SECTION23
from .sections.section24_nonworking_factors import ADAPTER as SECTION24
from .sections.section25_theory import ADAPTER as SECTION25
from .sections.section26_feedback import ADAPTER as SECTION26
from .sections.section27_lessons import ADAPTER as SECTION27


@dataclass(frozen=True)
class AdapterComposition:
    adapter_id: str
    part_id: str
    slots: dict[str, str]
    provenance: dict[str, tuple[str, ...]]
    fallback_slots: tuple[str, ...]


Composer = Callable[[dict, dict[str, str]], AdapterComposition]


_COMPOSERS: dict[str, Composer] = {
    "summary_5_blocks": compose_summary_ko,
}


SECTION_ADAPTERS: tuple[SectionHwpxAdapter, ...] = (
    SECTION01, SECTION02, SECTION03, SECTION04, SECTION05, SECTION06, SECTION07,
    SECTION08, SECTION09, SECTION10, SECTION11, SECTION12, SECTION13, SECTION14,
    SECTION15, SECTION16, SECTION17, SECTION18, SECTION19, SECTION20, SECTION21,
    SECTION22, SECTION23, SECTION24, SECTION25, SECTION26, SECTION27,
)
ADAPTER_BY_NUMBER = {adapter.spec.number: adapter for adapter in SECTION_ADAPTERS}
ADAPTER_BY_PART = {adapter.spec.part_id: adapter for adapter in SECTION_ADAPTERS}
SECTION_PIPELINES = tuple(adapter.spec for adapter in SECTION_ADAPTERS)
SPEC_BY_PART = {spec.part_id: spec for spec in SECTION_PIPELINES}
AUTHORING_SHAPES = {
    adapter.spec.part_id: adapter.authoring_shape for adapter in SECTION_ADAPTERS
}


def hwpx_authoring_contract(part_id: str) -> dict:
    adapter = ADAPTER_BY_PART[part_id]
    spec = adapter.spec
    authoring_shape = adapter.authoring_shape
    if part_id in NARRATIVE_OUTLINE_PART_IDS:
        authoring_shape += " " + NARRATIVE_OUTLINE_PROMPT
    return {
        "number": spec.number,
        "part_id": spec.part_id,
        "title": spec.title,
        "hwpx_path": spec.hwpx_path,
        "mode": spec.mode,
        "adapter": spec.adapter,
        "max_chars": spec.max_chars,
        "layout_rule": spec.layout_rule,
        "authoring_shape": authoring_shape,
        "source_module": adapter.source_module,
        "source_of_truth": "report_sections.content (plain text/Markdown)",
        "llm_role": "섹션 의미와 구조를 작성·수정하고 템플릿 적재 가능한 형태로 정리",
        "renderer_role": "고정된 문단·표 셀 주소에 값만 기록하고 원본 서식 보존",
    }


def validate_section_adapters() -> None:
    numbers = [adapter.spec.number for adapter in SECTION_ADAPTERS]
    part_ids = [adapter.spec.part_id for adapter in SECTION_ADAPTERS]
    adapter_ids = [adapter.spec.adapter for adapter in SECTION_ADAPTERS]
    source_modules = [adapter.source_module for adapter in SECTION_ADAPTERS]
    if numbers != list(range(1, 28)):
        raise RuntimeError(f"HWPX 섹션 번호가 1~27 순서가 아닙니다: {numbers}")
    for label, values in (
        ("part_id", part_ids),
        ("adapter_id", adapter_ids),
        ("source_module", source_modules),
    ):
        if len(values) != 27 or len(set(values)) != 27:
            raise RuntimeError(f"27개 HWPX 섹션의 {label}가 독립적이지 않습니다.")
    for adapter in SECTION_ADAPTERS:
        if not all(callable(item) for item in (
            adapter.normalize_section,
            adapter.prepare_section,
            adapter.patch_section_xml,
        )):
            raise RuntimeError(f"HWPX 섹션 어댑터 구현 누락: {adapter.spec.part_id}")


def apply_section_adapter_xml(
    section_number: int,
    xml: str,
    context: dict,
    prepared_sections: dict[str, str],
) -> SectionPatchResult:
    try:
        adapter = ADAPTER_BY_NUMBER[section_number]
    except KeyError as exc:
        raise RuntimeError(f"등록되지 않은 HWPX 섹션 번호입니다: {section_number}") from exc
    return adapter.patch_xml(xml, context, prepared_sections)


validate_section_adapters()


def compose_registered_adapter(
    adapter_id: str,
    context: dict,
    prepared_sections: dict[str, str],
) -> AdapterComposition:
    composer = _COMPOSERS.get(adapter_id)
    if composer is None:
        raise RuntimeError(f"등록되지 않은 HWPX 합성 adapter입니다: {adapter_id}")
    result = composer(context, prepared_sections)
    if result.adapter_id != adapter_id:
        raise RuntimeError(
            f"HWPX 합성 adapter 응답 불일치: requested={adapter_id}, returned={result.adapter_id}"
        )
    return result
