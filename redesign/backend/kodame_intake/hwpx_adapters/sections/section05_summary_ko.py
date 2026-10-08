from __future__ import annotations

from backend.oda_me.hwpx.adapters.summary_ko import render_summary_ko_document

from ..summary_ko import compose_summary_ko
from ._shared import build_adapter, normalize_with_contract, patch_review_section

PART_ID = "summary-ko"
MAX_CHARS = 11000

def normalize(value, normalizer): return normalize_with_contract(PART_ID, MAX_CHARS, value, normalizer)

def prepare(context, _raw_sections, prepared_sections, _evaluations):
    composition = compose_summary_ko(context, prepared_sections)
    return render_summary_ko_document(composition.slots), {
        "adapter_contract": "summary_5_blocks_v3",
        "block_count": len(composition.slots),
        "source_provenance": {
            key: list(value) for key, value in composition.provenance.items()
        },
        "deterministic_fallback_slots": list(composition.fallback_slots),
    }

def patch_xml(xml, context, prepared_sections): return patch_review_section(5, xml, context, prepared_sections)

ADAPTER = build_adapter(
    number=5, part_id=PART_ID, title="국문 요약", hwpx_path="Contents/section3.xml",
    mode="summary-document", adapter_id="summary_5_blocks", max_chars=MAX_CHARS,
    layout_rule="초안의 (1)~(5) 상위 항목과 하위 문단을 내용 변경 없이 4쪽 이상 조판하고 1.·(1)·ㅇ 앞 한 줄 여백을 보장",
    authoring_shape="(1) 대상사업개요, (2) 평가개요, (3) 성과달성도, (4) 기준별 평가결과, (5) 결론의 고정 순서로 쓰고 각 항목은 ㅇ 요지와 - 세부 판단으로 구성한다. ㅇ 앞에는 공백 1회, - 앞에는 공백을 두지 않으며 HWPX 문단 스타일로만 하위 들여쓰기를 적용한다. 괄호형 세부 요약은 큰 논거 구분이 필요한 경우에만 선택적으로 사용한다. 총 5,600~9,000자와 4쪽 이상의 조판 분량을 확보한다.",
    normalize_section=normalize, prepare_section=prepare, patch_section_xml=patch_xml, source_module=__name__,
)
