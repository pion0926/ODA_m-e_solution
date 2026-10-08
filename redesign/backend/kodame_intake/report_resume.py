"""Resume only successful sections of the selected run with unchanged inputs."""
from .project_lifecycle import snapshots_match


def resumable_parts(run, sections, snapshot):
    if run.get("status") not in {"failed", "cancelled", "completed_with_errors"}:
        raise ValueError("중단되거나 일부 실패한 작업만 이어서 생성할 수 있습니다.")
    if not snapshots_match(run.get("input_snapshot"), snapshot):
        raise ValueError("자료 또는 평가가 변경되었거나 이전 작업의 복구 정보가 없습니다. 최신 자료로 새로 작성해 주세요.")
    inherited = set(run.get("resume_part_ids") or [])
    result = []
    for section in sections:
        metadata = section.get("generation_metadata") or {}
        belongs = metadata.get("generation_run_id") == str(run["id"]) or section["part_id"] in inherited
        if (belongs and section.get("status") not in {"failed", "generating", "empty"}
                and str(section.get("content") or "").strip()
                and snapshots_match(metadata.get("input_snapshot"), snapshot)):
            result.append(section["part_id"])
    return result
