from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class PastTopicRecord(TypedDict):
    """A previously completed research item available for reuse or comparison."""

    question: str
    report: "FinalReport" # Forward reference to avoid circular dependency
    user_id: str
    created_at: str

class ReportSource(TypedDict):
    """A source cited in a draft report."""

    title: str
    url:   str

class SearchResult(TypedDict):
    """A normalized result captured from an external search tool."""

    tool_name: str
    title: str
    url: str
    snippet: str
    score: float
    source_type: str
    chunk_id: str


class SelectedEvidence(TypedDict):
    """Evidence explicitly chosen by the user for report generation."""

    tool_name: str
    title: str
    url: str
    snippet: str
    score: float
    source_type: str
    chunk_id: str


class GuardrailState(TypedDict):
    """Question-level validation and risk assessment for the current run."""

    sanitized_question: str
    status: str
    recommended_action: str
    warnings: list[str]
    risk_flags: list[str]
    allowed_tools: list[str]
    explanation: str
    clarifying_question: str


class RunMetrics(TypedDict):
    """Operational metrics captured during the current research run."""

    iterations_used: int
    evidence_items: int
    unique_sources: int
    history_candidates: int
    retrieval_strategy: str
    rerank_applied: int
    rerank_candidates: int
    rerank_duplicates_removed: int
    rerank_trimmed_for_limit: int
    rerank_distinct_sources: int


class HistoryReview(TypedDict):
    """Assessment of how the current question relates to prior published work."""

    match_type: str
    rationale: str
    relevant_history: list[PastTopicRecord]


class DraftReport(TypedDict):
    """Structured intermediate report prepared before final publishing."""

    title: str
    findings: list[str]
    sources: list[ReportSource]
    confidence: float
    summary: str


class FinalReport(TypedDict):
    """Structured final report ready for display or downstream reuse."""

    title: str
    summary: str
    key_findings: list[str]
    sources: list[ReportSource]
    confidence: float
    published_report: str

class ResearchState(TypedDict, total=False):
    """Shared graph state for the Deep Research Agent."""

    # Core inputs
    question: str
    user_id:  str

    # Running conversation and tool trace
    messages: Annotated[list[BaseMessage], add_messages]

    # Loop control
    iteration:      int
    max_iterations: int
    reasoner_decision: str

    # Cross-session memory and current-run research context
    # `past_topics` is a shared pool of prior question/report pairs, not only
    # the current user's own history.
    past_topics:    list[PastTopicRecord]
    history_review: HistoryReview
    history_decision: str
    reused_topic: PastTopicRecord
    retrieval_context: list[SearchResult]
    search_results: list[SearchResult]
    selected_evidence_ids: list[str]
    selected_evidence: list[SelectedEvidence]
    research_plan: list[str]
    guardrails: GuardrailState
    run_metrics: RunMetrics

    # Report lifecycle
    draft_report: DraftReport
    review_decision: str
    human_feedback:  str
    final_report:    FinalReport
