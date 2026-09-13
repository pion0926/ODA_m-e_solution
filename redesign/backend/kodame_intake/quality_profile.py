from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


PROFILE_ENV = "REPORT_QUALITY_PROFILE_PATH"
DEFAULT_PROFILE_PATH = Path.cwd() / "config" / "report_quality_profile.json"
CONTAINER_PROFILE_PATH = Path("/app/config/report_quality_profile.json")


def _profile_path() -> Path:
    configured = os.getenv(PROFILE_ENV, "").strip()
    if configured:
        return Path(configured)
    if CONTAINER_PROFILE_PATH.exists():
        return CONTAINER_PROFILE_PATH
    return DEFAULT_PROFILE_PATH


def _require_list(value: Any, name: str) -> list:
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"보고서 품질 프로필 {name}은 비어 있지 않은 배열이어야 합니다.")
    return value


def _validate(profile: dict[str, Any]) -> dict[str, Any]:
    if int(profile.get("version") or 0) != 1:
        raise RuntimeError("지원하지 않는 보고서 품질 프로필 버전입니다.")
    layout = profile.get("layout")
    writing = profile.get("writing")
    if not isinstance(layout, dict) or not isinstance(writing, dict):
        raise RuntimeError("보고서 품질 프로필의 layout/writing 구성이 누락되었습니다.")

    grade_groups = _require_list(
        (layout.get("grade_table") or {}).get("page_row_groups"),
        "layout.grade_table.page_row_groups",
    )
    if len(grade_groups) != 2 or sorted({row for group in grade_groups for row in group}) != list(range(20)):
        raise RuntimeError("평가등급표는 머리행을 반복하는 2쪽 구성으로 전체 20개 행을 포함해야 합니다.")

    pdm_groups = _require_list(
        (layout.get("pdm_table") or {}).get("page_row_groups"),
        "layout.pdm_table.page_row_groups",
    )
    if sorted({row for group in pdm_groups for row in group}) != list(range(9)):
        raise RuntimeError("PDM 표 분할은 머리행을 반복하며 전체 9개 행을 포함해야 합니다.")

    achievement_groups = _require_list(
        (layout.get("achievement_table") or {}).get("page_item_groups"),
        "layout.achievement_table.page_item_groups",
    )
    if sorted(item for group in achievement_groups for item in group) != list(range(14)):
        raise RuntimeError("성과달성도 표 분할은 14개 지표를 중복 없이 모두 포함해야 합니다.")

    matrix_groups = _require_list(
        (layout.get("evaluation_matrix_table") or {}).get("page_row_groups"),
        "layout.evaluation_matrix_table.page_row_groups",
    )
    if any(not group or group[0] != 0 for group in matrix_groups):
        raise RuntimeError("평가매트릭스의 모든 분할 표는 머리행 0을 반복해야 합니다.")
    if sorted({row for group in matrix_groups for row in group}) != list(range(9)):
        raise RuntimeError("평가매트릭스 표 분할은 전체 8개 기준 행을 중복 없이 포함해야 합니다.")
    narrative_layout = writing.get("narrative_detail_layout")
    if not isinstance(narrative_layout, dict):
        raise RuntimeError("writing.narrative_detail_layout 구성이 누락되었습니다.")
    maximum_characters = int(narrative_layout.get("maximum_characters") or 0)
    maximum_sentences = int(narrative_layout.get("maximum_sentences") or 0)
    if not 240 <= maximum_characters <= 600 or not 2 <= maximum_sentences <= 6:
        raise RuntimeError("서술형 문단 시각 예산은 240~600자, 2~6문장 범위여야 합니다.")
    return profile


@lru_cache(maxsize=1)
def report_quality_profile() -> dict[str, Any]:
    path = _profile_path()
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"보고서 품질 프로필을 찾을 수 없습니다: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"보고서 품질 프로필 JSON 오류({path}): {exc}") from exc
    return _validate(profile)


def layout_profile(name: str) -> dict[str, Any]:
    value = (report_quality_profile().get("layout") or {}).get(name)
    if not isinstance(value, dict):
        raise KeyError(f"등록되지 않은 보고서 레이아웃 프로필: {name}")
    return value


def writing_profile() -> dict[str, Any]:
    return dict(report_quality_profile().get("writing") or {})


def toc_project_overrides(project_title: object) -> dict[str, str]:
    title = str(project_title or "").strip()
    overrides = (
        (report_quality_profile().get("rhwp_toc") or {}).get("project_overrides") or {}
    )
    if not isinstance(overrides, dict):
        return {}
    exact = overrides.get(title)
    if isinstance(exact, dict):
        return {str(key): str(value) for key, value in exact.items()}
    for pattern, value in overrides.items():
        if pattern.startswith("contains:") and pattern.removeprefix("contains:") in title and isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
    return {}
