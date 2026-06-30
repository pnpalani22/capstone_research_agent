from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReportSourceModel(StrictBaseModel):
    title: str = Field(min_length=1)
    url: str = ""


class SearchResultModel(StrictBaseModel):
    tool_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = ""
    snippet: str = Field(min_length=1, max_length=700)
    score: float = Field(ge=0.0, le=1.0)
    source_type: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)


class SelectedEvidenceModel(SearchResultModel):
    pass


GuardrailStatus = Literal["ready", "needs_clarification", "blocked"]
GuardrailAction = Literal["proceed", "revise", "block"]
GuardrailTool = Literal["tavily", "wikipedia", "weather"]
GuardrailRiskFlag = Literal[
    "prompt_injection",
    "secret_exfiltration",
    "policy_bypass",
    "overscoped_request",
    "non_research_request",
]


class GuardrailEvaluationModel(StrictBaseModel):
    status: GuardrailStatus
    recommended_action: GuardrailAction
    warnings: list[str] = Field(default_factory=list, max_length=6)
    risk_flags: list[GuardrailRiskFlag] = Field(default_factory=list, max_length=5)
    allowed_tools: list[GuardrailTool] = Field(default_factory=lambda: ["tavily", "wikipedia", "weather"], min_length=1, max_length=3)
    explanation: str = Field(min_length=1, max_length=240)
    clarifying_question: str = Field(default="", max_length=240)


class GuardrailStateModel(StrictBaseModel):
    sanitized_question: str = Field(min_length=3, max_length=600)
    status: GuardrailStatus
    recommended_action: GuardrailAction
    warnings: list[str] = Field(default_factory=list, max_length=6)
    risk_flags: list[GuardrailRiskFlag] = Field(default_factory=list, max_length=5)
    allowed_tools: list[GuardrailTool] = Field(default_factory=lambda: ["tavily", "wikipedia", "weather"], min_length=1, max_length=3)
    explanation: str = Field(min_length=1, max_length=240)
    clarifying_question: str = Field(default="", max_length=240)


class RunMetricsModel(StrictBaseModel):
    iterations_used: int = Field(ge=0)
    evidence_items: int = Field(ge=0)
    unique_sources: int = Field(ge=0)
    history_candidates: int = Field(ge=0)
    retrieval_strategy: str = Field(min_length=1)
    rerank_applied: int = Field(ge=0, le=1)
    rerank_candidates: int = Field(ge=0)
    rerank_duplicates_removed: int = Field(ge=0)
    rerank_trimmed_for_limit: int = Field(ge=0)
    rerank_distinct_sources: int = Field(ge=0)


class DraftReportModel(StrictBaseModel):
    title: str = Field(min_length=1)
    findings: list[str] = Field(default_factory=list, min_length=3, max_length=6)
    sources: list[ReportSourceModel] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=240)


class FinalReportModel(StrictBaseModel):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=240)
    key_findings: list[str] = Field(default_factory=list)
    sources: list[ReportSourceModel] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    published_report: str = Field(min_length=1, max_length=3200)


class PastTopicRecordModel(StrictBaseModel):
    question: str = Field(min_length=1)
    report: FinalReportModel
    user_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)


class HistoryReferenceModel(StrictBaseModel):
    question: str = Field(min_length=1)
    created_at: str = Field(min_length=1)


class HistoryReviewModel(StrictBaseModel):
    match_type: Literal["similar", "related", "new"]
    rationale: str = Field(min_length=1)
    relevant_history: list[HistoryReferenceModel] = Field(default_factory=list, max_length=3)


class ResearchPlanModel(StrictBaseModel):
    queries: list[str] = Field(min_length=2, max_length=3)


class ReasonerDecisionModel(StrictBaseModel):
    decision: Literal["CONTINUE", "DONE"]
    reason: str = Field(min_length=1)


class PublishedAnswerModel(StrictBaseModel):
    published_report: str = Field(min_length=1, max_length=3200)


class HistoryMatchModel(StrictBaseModel):
    question: str = Field(min_length=1)
    published_report: str = ""
    title: str = ""
    summary: str = ""
    user_id: str = ""
    created_at: str = ""


class HistoryInterruptModel(StrictBaseModel):
    action: Literal["review_history_match"]
    current_question: str = Field(min_length=1)
    match_type: Literal["similar", "related", "new"]
    rationale: str = Field(min_length=1)
    matches: list[HistoryMatchModel] = Field(default_factory=list)
    reuse_allowed: bool = False
    reuse_candidate: HistoryMatchModel | None = None


class EvidenceSelectionInterruptModel(StrictBaseModel):
    action: Literal["select_evidence_for_report"]
    question: str = Field(min_length=1)
    research_plan: list[str] = Field(default_factory=list)
    current_evidence: list[SearchResultModel] = Field(default_factory=list)
    instructions: str = Field(min_length=1)


class ReviewInterruptModel(StrictBaseModel):
    action: Literal["review_before_publish"]
    question: str = Field(min_length=1)
    iterations: int = Field(ge=0)
    draft: DraftReportModel


class CreateSessionResponse(StrictBaseModel):
    thread_id: str = Field(min_length=1)


class TranslateTextRequest(StrictBaseModel):
    text: str = Field(min_length=1, max_length=3200)
    target_language: str = Field(min_length=2, max_length=16)


class TranslateTextResponse(StrictBaseModel):
    translated_text: str = Field(min_length=1, max_length=5000)
    target_language: str = Field(min_length=2, max_length=16)


class StartResearchRequest(StrictBaseModel):
    thread_id: str = Field(min_length=1)
    question: str
    user_id: str = Field(min_length=1)
    max_iterations: int = Field(default=2, ge=1, le=6)

    @field_validator("question")
    @classmethod
    def validate_question_length(cls, value: str) -> str:
        question = value.strip()
        if len(question) < 8:
            raise ValueError("Question is too short. Please enter at least 8 characters.")
        if len(question) > 600:
            raise ValueError("Question is too long. Please keep it under 600 characters.")
        return question


class ResumeResearchRequest(StrictBaseModel):
    thread_id: str = Field(min_length=1)
    decision: Literal[
        "proceed_with_context",
        "start_fresh_plan",
        "reuse_existing",
        "selected_evidence",
        "approved",
        "edited",
        "rejected",
    ]
    selected_evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    human_feedback: str = Field(default="", max_length=800)


class RunSnapshotResponse(StrictBaseModel):
    thread_id: str = Field(min_length=1)
    status: Literal["idle", "waiting_input", "completed"]
    question: str = ""
    user_id: str = ""
    max_iterations: int = Field(default=0, ge=0)
    research_plan: list[str] = Field(default_factory=list)
    history_decision: str = ""
    review_decision: str = ""
    guardrails: GuardrailStateModel | None = None
    run_metrics: RunMetricsModel | None = None
    interrupt: HistoryInterruptModel | EvidenceSelectionInterruptModel | ReviewInterruptModel | None = None
    draft_report: DraftReportModel | None = None
    search_results: list[SearchResultModel] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    selected_evidence: list[SelectedEvidenceModel] = Field(default_factory=list)
    final_report: FinalReportModel | None = None
    reused_topic: PastTopicRecordModel | None = None
