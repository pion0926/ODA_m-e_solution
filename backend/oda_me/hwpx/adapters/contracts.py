from __future__ import annotations

from dataclasses import dataclass


class AdapterContractError(RuntimeError):
    """Raised before a template is changed when an adapter contract is invalid."""


@dataclass(frozen=True)
class SlotContract:
    key: str
    paragraph_index: int
    outline_kind: str
    para_pr_id: int
    char_pr_id: int
    source_parts: tuple[str, ...]
    max_chars: int
    authoring_prefix: str
    rendered_prefix: str
    redundant_parent_label: str = ""
    min_body_chars: int = 8


@dataclass(frozen=True)
class AdapterContract:
    adapter_id: str
    part_id: str
    schema: str
    section_number: int
    hwpx_path: str
    slots: tuple[SlotContract, ...]

    @property
    def slot_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.slots)

    @property
    def slots_by_key(self) -> dict[str, SlotContract]:
        return {slot.key: slot for slot in self.slots}

    def validate_definition(self) -> None:
        keys = self.slot_keys
        paragraph_indices = tuple(slot.paragraph_index for slot in self.slots)
        if len(keys) != len(set(keys)):
            raise AdapterContractError(f"{self.adapter_id}: 중복 슬롯 키가 있습니다.")
        if len(paragraph_indices) != len(set(paragraph_indices)):
            raise AdapterContractError(f"{self.adapter_id}: 중복 문단 주소가 있습니다.")
        if any(slot.outline_kind not in {"subheading", "bullet", "detail"} for slot in self.slots):
            raise AdapterContractError(f"{self.adapter_id}: 지원하지 않는 문단 계층이 있습니다.")
        if any(slot.max_chars <= 0 or slot.min_body_chars <= 0 for slot in self.slots):
            raise AdapterContractError(f"{self.adapter_id}: 슬롯 길이 계약이 올바르지 않습니다.")
