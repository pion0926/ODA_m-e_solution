from __future__ import annotations
from pydantic import BaseModel, Field


class ReportSectionUpdate(BaseModel):
    content: str = Field(max_length=200000)
    expected_updated_at: str | None = Field(default=None, max_length=80)


class ReportGenerationRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    current_content: str | None = Field(default=None, max_length=200000)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RegistrationRequest(LoginRequest):
    display_name: str = Field(min_length=2, max_length=80)


class AccountSettingsUpdate(BaseModel):
    llm_model: str = Field(min_length=3, max_length=120)


class PerformanceReviewRequest(BaseModel):
    revision: str = Field(min_length=64, max_length=64)
    mappings: dict[str, list[str]]


class ProjectAIUpdate(BaseModel):
    llm_model: str = Field(min_length=3, max_length=120)
    expected_revision: int = Field(ge=0)


class MenuPermissionsUpdate(BaseModel):
    menu_permissions: dict[str, bool]


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    supported_locales: list[str] = Field(min_length=1, max_length=5)
    default_locale: str = Field(min_length=2, max_length=10)
    account_ids: list[str] = Field(default_factory=list, max_length=100)


class ProjectLocaleUpdate(BaseModel):
    locale: str = Field(min_length=2, max_length=10)


class IntakeModeRequest(BaseModel):
    mode: str = Field(pattern='^(artifact|evidence)$')
    expected_updated_at: str


class EvaluationScopeRequest(BaseModel):
    excluded: bool
    reason: str = Field(min_length=1, max_length=1000)
    expected_updated_at: str


class DacReviewRequest(BaseModel):
    revision: str
    mappings: dict[str, list[str]]
    full_questions: list[str] = []
