from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SectionPipelineSpec:
    number: int
    part_id: str
    title: str
    hwpx_path: str
    mode: str
    adapter: str
    max_chars: int
    layout_rule: str


@dataclass(frozen=True)
class SectionPatchResult:
    xml: str
    changed: int
    metrics: dict[str, int | str | bool]


CommonNormalizer = Callable[[str, str, int | None], tuple[str, dict]]
NormalizeSection = Callable[[str, CommonNormalizer], tuple[str, dict]]
PreparedSection = str | tuple[str, dict]
PrepareSection = Callable[[dict, dict[str, str], dict[str, str], list[dict]], PreparedSection]
PatchSection = Callable[[str, dict, dict[str, str]], SectionPatchResult]


@dataclass(frozen=True)
class SectionHwpxAdapter:
    """One independently editable logical-section conversion pipeline."""

    spec: SectionPipelineSpec
    authoring_shape: str
    normalize_section: NormalizeSection
    prepare_section: PrepareSection
    patch_section_xml: PatchSection
    source_module: str

    def normalize(self, value: str, normalizer: CommonNormalizer) -> tuple[str, dict]:
        return self.normalize_section(value, normalizer)

    def prepare(
        self,
        context: dict,
        raw_sections: dict[str, str],
        prepared_sections: dict[str, str],
        evaluations: list[dict],
    ) -> PreparedSection:
        return self.prepare_section(context, raw_sections, prepared_sections, evaluations)

    def patch_xml(
        self,
        xml: str,
        context: dict,
        prepared_sections: dict[str, str],
    ) -> SectionPatchResult:
        return self.patch_section_xml(xml, context, prepared_sections)
