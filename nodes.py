from __future__ import annotations

import ast
import json
import math
import re
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from history_store import (
    load_persisted_history,
    merge_history_records,
    save_persisted_history,
    sort_history_records,
)

from prompts import (
    GUARDRAIL_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from schemas import (
    DraftReportModel,
    FinalReportModel,
    GuardrailEvaluationModel,
    GuardrailStateModel,
)
from state import ResearchState

SUMMARY_CHAR_LIMIT = 240
QUESTION_CHAR_LIMIT = 600
EVIDENCE_SNIPPET_LIMIT = 620
MAX_EVIDENCE_ITEMS = 8
MAX_HISTORY_CHUNKS = 3
MAX_CHUNKS_PER_SOURCE = 2
MIN_HISTORY_RELEVANCE_SCORE = 0.32
MAX_SEARCH_RESULTS_FOR_PROMPT = 4
MAX_HISTORY_ITEMS_FOR_PROMPT = 3
MIN_REASONER_EVIDENCE_ITEMS = 3
MIN_REASONER_UNIQUE_SOURCES = 2
DEFAULT_ALLOWED_TOOLS = ["tavily", "wikipedia", "weather"]
DOMAIN_TOOL_KEYWORDS = {
    "weather": {
        "weather",
        "forecast",
        "temperature",
        "rain",
        "humidity",
        "wind",
        "storm",
        "climate",
        "snow",
        "storm",
    },
}
HIGH_SEVERITY_RISK_FLAGS = {"prompt_injection", "secret_exfiltration", "policy_bypass"}
HISTORY_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "this",
    "to",
    "under",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "will",
    "would",
    "language",
    "languages",
    "model",
    "models",
    "understanding",
    "context",
    "task",
    "tasks",
    "text",
    "heavy",
    "long",
}
QUESTION_STOPWORDS = HISTORY_STOPWORDS | {
    "about",
    "analysis",
    "compare",
    "comparison",
    "current",
    "effect",
    "effects",
    "impact",
    "overview",
    "research",
    "study",
    "topic",
    "using",
}
QUESTION_RISK_PATTERNS = {
    "prompt_injection": re.compile(r"ignore\s+(all|any|previous)|system\s+prompt|developer\s+message", re.IGNORECASE),
    "secret_exfiltration": re.compile(r"api\s*key|token|password|secret", re.IGNORECASE),
    "policy_bypass": re.compile(r"bypass\s+(safety|policy|guardrails)|jailbreak|disable\s+(safety|guardrails)", re.IGNORECASE),
    "non_research_request": re.compile(
        r"\b(run|install|start|launch|restart|stop|deploy|build|execute|create|open|fix|debug)\b",
        re.IGNORECASE,
    ),
}


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _compact_whitespace(value: str) -> str:
    """Normalize whitespace so summary limits are applied consistently."""

    return " ".join(value.split())


def _truncate_text(value: Any, limit: int) -> str:
    """Convert tool output to text and keep only a short excerpt."""

    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, default=str)

    if len(text) <= limit:
        return text

    return text[:limit].rstrip() + "..."


def _sanitize_question(value: str) -> str:
    """Normalize and cap the incoming research question."""

    cleaned = _compact_whitespace(str(value or ""))
    return cleaned[:QUESTION_CHAR_LIMIT].strip()


def _dedupe_text_list(values: list[str]) -> list[str]:
    """Keep a stable order while removing empty or duplicate strings."""

    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        item = _compact_whitespace(str(value or ""))
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _extract_keywords(value: str, *, limit: int = 6) -> list[str]:
    """Pull a compact set of search-friendly keywords from free text."""

    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", _compact_whitespace(value).lower())
        if len(token) > 2 and token not in QUESTION_STOPWORDS
    ]
    return _dedupe_text_list(tokens)[:limit]


def _build_local_research_plan(question: str, guardrails: dict[str, Any], relevant_history: list[dict[str, Any]]) -> list[str]:
    """Create a lightweight 2-3 query plan without another model call."""

    keywords = _extract_keywords(question, limit=6)
    if not keywords:
        keywords = _extract_keywords(str(guardrails.get("sanitized_question", question)), limit=6)

    core = " ".join(keywords[:4]) or _sanitize_question(question)
    if len(core) > 120:
        core = core[:120].rstrip()

    allowed_tools = {str(item).strip().lower() for item in guardrails.get("allowed_tools", DEFAULT_ALLOWED_TOOLS)}
    queries: list[str] = []

    if core:
        queries.append(core)
        queries.append(f"{core} evidence tradeoffs")

    if relevant_history:
        prior_topic = _truncate_summary(str(relevant_history[0].get("question", "")), 60)
        if prior_topic:
            queries.append(f"{core} update since {prior_topic}")

    if "weather" in allowed_tools:
        queries.append(f"{core} current conditions")
    else:
        queries.append(f"{core} background context")

    return _dedupe_text_list(queries)[:3]


def _build_history_rationale(match_type: str, top_score: float, matched_count: int) -> str:
    """Generate a short explanation for the local history decision."""

    if match_type == "similar":
        return f"Prior work is very close to the current question (score {top_score:.2f}, {matched_count} relevant record(s))."
    if match_type == "related":
        return f"Prior work overlaps the current question at a moderate level (score {top_score:.2f}, {matched_count} relevant record(s))."
    return "No prior research record was similar enough to reuse."


def _classify_history_locally(
    question: str,
    past_topics: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    """Pick a history relation without spending a model call on obvious matches."""

    scored_history = [
        (item, _history_relevance_score(question, item))
        for item in past_topics
    ]
    scored_history = [(item, score) for item, score in scored_history if score >= MIN_HISTORY_RELEVANCE_SCORE]
    scored_history.sort(key=lambda pair: pair[1], reverse=True)

    if not scored_history:
        return "new", "No prior published research records were relevant to the current question.", []

    top_item, top_score = scored_history[0]
    relevant_history = [item for item, _ in scored_history[:MAX_HISTORY_CHUNKS]]

    exact_match = _find_newest_exact_history_match(question, past_topics)
    if exact_match is not None:
        if exact_match not in relevant_history:
            relevant_history.insert(0, exact_match)
        return "similar", _build_history_rationale("similar", 1.0, len(relevant_history)), relevant_history[:3]

    if top_score >= 0.78:
        return "similar", _build_history_rationale("similar", top_score, len(relevant_history)), relevant_history[:3]

    if top_score >= 0.48:
        return "related", _build_history_rationale("related", top_score, len(relevant_history)), relevant_history[:3]

    return "new", _build_history_rationale("new", top_score, len(relevant_history)), []


def _decide_reasoner_locally(state: ResearchState) -> tuple[str, str]:
    """Use simple evidence thresholds to avoid a model call when the answer is obvious."""

    iteration = int(state.get("iteration", 0) or 0)
    max_iterations = int(state.get("max_iterations", 3) or 3)
    search_results = list(state.get("search_results", []))
    unique_sources = len({_source_identity(item) for item in search_results})
    evidence_count = len(search_results)
    best_score = max((float(item.get("score", 0.0)) for item in search_results), default=0.0)

    if iteration >= max_iterations:
        return "DONE", f"Loop guard reached at iteration {iteration}."

    if evidence_count < MIN_REASONER_EVIDENCE_ITEMS:
        return "CONTINUE", f"Only {evidence_count} evidence item(s) are available so far."

    if unique_sources < MIN_REASONER_UNIQUE_SOURCES and iteration < max_iterations - 1:
        return "CONTINUE", f"Need broader source coverage before synthesis ({unique_sources} unique source(s))."

    if evidence_count >= 5 and unique_sources >= MIN_REASONER_UNIQUE_SOURCES:
        return "DONE", f"Enough evidence gathered across {unique_sources} sources."

    if best_score >= 0.72 and unique_sources >= MIN_REASONER_UNIQUE_SOURCES:
        return "DONE", f"High-signal evidence is available (top score {best_score:.2f})."

    if iteration >= max_iterations - 1 and evidence_count >= MIN_REASONER_EVIDENCE_ITEMS:
        return "DONE", f"Final iteration reached with {evidence_count} evidence item(s)."

    return "CONTINUE", f"Keep searching to improve source diversity and confidence ({evidence_count} item(s), {unique_sources} source(s))."


def _format_final_report(draft_report: dict[str, Any], question: str, human_feedback: str = "") -> str:
    """Create a concise final report without asking the model to rewrite it."""

    title = draft_report.get("title") or f"Research Report: {question}"
    summary = _truncate_summary(draft_report.get("summary", ""))
    if human_feedback.strip():
        summary = _truncate_summary(f"{summary} Reviewer note: {human_feedback.strip()}")

    findings = [
        _truncate_summary(str(item), 140)
        for item in (draft_report.get("findings") or [])[:5]
        if _compact_whitespace(str(item))
    ]
    sources = _normalize_sources(draft_report.get("sources", []))[:4]

    lines = [f"# {title}", "", f"Summary: {summary}"]
    if findings:
        lines.append("")
        lines.append("Key findings:")
        for item in findings:
            lines.append(f"- {item}")
    if sources:
        lines.append("")
        lines.append("Sources:")
        for source in sources:
            source_title = source.get("title", "Untitled source")
            source_url = source.get("url", "")
            lines.append(f"- {source_title}{f' ({source_url})' if source_url else ''}")

    confidence = draft_report.get("confidence", 0.5)
    lines.extend(["", f"Confidence: {float(confidence):.2f}"])
    return "\n".join(lines).strip()


def _infer_allowed_tools(question: str) -> list[str]:
    """Choose domain-specific tools when the question clearly asks for them."""

    normalized = _compact_whitespace(question).lower()
    allowed = ["tavily", "wikipedia"]

    for tool_name, keywords in DOMAIN_TOOL_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            allowed.append(tool_name)

    return _dedupe_text_list(allowed)


def _guardrail_explanation(status: str, risk_flags: list[str], warnings: list[str]) -> str:
    """Generate a concise explanation for the guardrail decision."""

    if status == "blocked":
        if risk_flags:
            return (
                "The request was blocked because it asks for hidden instructions, credentials, or a safety bypass "
                f"({', '.join(risk_flags)})."
            )
        return "The request was blocked because it falls outside the allowed research workflow."

    if status == "needs_clarification":
        if warnings:
            return warnings[0]
        return "The request needs more scope or context before research should begin."

    return "The request is suitable for research and can proceed with the allowed tools."


def _assess_question(question: str) -> dict[str, Any]:
    """Apply deterministic intake guardrails before any model-based evaluation."""

    sanitized_question = _sanitize_question(question)
    warnings: list[str] = []
    risk_flags: list[str] = []

    if len(sanitized_question.split()) < 5:
        warnings.append("Question is brief; add business context, scope, or constraints for better retrieval.")
    if len(sanitized_question) > 420:
        warnings.append("Question is long; prioritize the key decision or outcome to improve search precision.")
    if len(sanitized_question.split()) > 90:
        risk_flags.append("overscoped_request")
        warnings.append("Question is overscoped; focus on one decision, market, or outcome for better research quality.")

    for flag, pattern in QUESTION_RISK_PATTERNS.items():
        if flag == "non_research_request":
            is_operational_request = (
                pattern.search(sanitized_question)
                and (
                    re.search(r"\b(for me|please)\b", sanitized_question, re.IGNORECASE)
                    or re.search(r"\b(npm|server|frontend|backend|docker|api|package|script|file|directory|port|command)\b", sanitized_question, re.IGNORECASE)
                )
            )
            if is_operational_request:
                risk_flags.append(flag)
            continue
        if pattern.search(sanitized_question):
            risk_flags.append(flag)

    should_request_clarification = (
        len(sanitized_question.split()) < 5
        or len(sanitized_question) > 420
        or len(sanitized_question.split()) > 90
    )
    status = "needs_clarification" if should_request_clarification else "ready"
    recommended_action = "revise" if status == "needs_clarification" or warnings else "proceed"
    if any(flag in HIGH_SEVERITY_RISK_FLAGS for flag in risk_flags):
        status = "blocked"
        recommended_action = "block"
    elif "non_research_request" in risk_flags:
        status = "blocked"
        recommended_action = "block"

    guardrails = {
        "sanitized_question": sanitized_question,
        "status": status,
        "recommended_action": recommended_action,
        "warnings": _dedupe_text_list(warnings)[:6],
        "risk_flags": _dedupe_text_list(risk_flags)[:5],
        "allowed_tools": _infer_allowed_tools(sanitized_question),
        "explanation": "",
        "clarifying_question": "Please restate the request as a focused research question with scope and desired outcome." if status == "needs_clarification" else "",
    }
    guardrails["explanation"] = _guardrail_explanation(
        guardrails["status"],
        guardrails["risk_flags"],
        guardrails["warnings"],
    )
    return GuardrailStateModel.model_validate(guardrails).model_dump()


def _merge_guardrail_state(base: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Merge deterministic and model-based guardrail signals into one strict state object."""

    status = evaluation.get("status", base.get("status", "ready"))
    if base.get("status") == "blocked" or any(flag in HIGH_SEVERITY_RISK_FLAGS for flag in evaluation.get("risk_flags", [])):
        status = "blocked"
    elif base.get("status") == "needs_clarification" or status == "needs_clarification":
        status = "needs_clarification"
    else:
        status = "ready"

    recommended_action = evaluation.get("recommended_action", base.get("recommended_action", "proceed"))
    if status == "blocked":
        recommended_action = "block"
    elif status == "ready":
        recommended_action = "proceed"
    elif status == "needs_clarification" and recommended_action == "proceed":
        recommended_action = "revise"

    merged = {
        "sanitized_question": base.get("sanitized_question", ""),
        "status": status,
        "recommended_action": recommended_action,
        "warnings": _dedupe_text_list(list(base.get("warnings", [])) + list(evaluation.get("warnings", [])))[:6],
        "risk_flags": _dedupe_text_list(list(base.get("risk_flags", [])) + list(evaluation.get("risk_flags", [])))[:5],
        "allowed_tools": list(dict.fromkeys(list(evaluation.get("allowed_tools", [])) or list(base.get("allowed_tools", DEFAULT_ALLOWED_TOOLS))))[:3],
        "explanation": _compact_whitespace(str(evaluation.get("explanation") or base.get("explanation") or "")),
        "clarifying_question": _compact_whitespace(str(evaluation.get("clarifying_question") or base.get("clarifying_question") or "")),
    }

    if not merged["explanation"]:
        merged["explanation"] = _guardrail_explanation(merged["status"], merged["risk_flags"], merged["warnings"])
    if merged["status"] == "needs_clarification" and not merged["clarifying_question"]:
        merged["clarifying_question"] = "Please restate the request as a focused research question with scope and desired outcome."

    return GuardrailStateModel.model_validate(merged).model_dump()


def evaluate_guardrails_node(state: ResearchState, *, llm) -> dict[str, Any]:
    """Use structured prompt evaluation to refine intake guardrails before research begins."""

    base_guardrails = _assess_question(state.get("question", ""))
    prompt = [
        SystemMessage(content=GUARDRAIL_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research question: {base_guardrails['sanitized_question']}\n\n"
                f"Deterministic intake assessment: {json.dumps(base_guardrails, default=str)}\n\n"
                "Return the strict guardrail evaluation for this request."
            )
        ),
    ]

    try:
        evaluation = llm.with_structured_output(GuardrailEvaluationModel).invoke(prompt).model_dump()
        guardrails = _merge_guardrail_state(base_guardrails, evaluation)
    except Exception:
        guardrails = base_guardrails

    return {
        "question": guardrails["sanitized_question"],
        "guardrails": guardrails,
        "messages": [AIMessage(content=f"Guardrail assessment: {json.dumps(guardrails, default=str)}")],
    }


def route_after_guardrail_evaluation(state: ResearchState) -> str:
    """Stop early when the intake guardrails block the request."""

    if state.get("guardrails", {}).get("status") == "blocked":
        return "blocked"
    return "continue"


def guardrail_block_node(state: ResearchState) -> dict[str, Any]:
    """Return a final blocked response instead of entering the research loop."""

    guardrails = state.get("guardrails", {})
    explanation = _truncate_summary(guardrails.get("explanation") or "The request was blocked by research guardrails.")
    risks = guardrails.get("risk_flags", [])
    clarifying_question = guardrails.get("clarifying_question") or (
        "Submit a neutral research question that does not ask for secrets, hidden instructions, or safety bypasses."
    )
    findings = [
        "The request was stopped before search and synthesis began.",
        f"Detected risk flags: {', '.join(risks)}." if risks else "The request conflicts with the allowed research workflow.",
        clarifying_question,
    ]
    final_report = FinalReportModel.model_validate(
        {
            "title": "Request blocked by research guardrails",
            "summary": explanation,
            "key_findings": findings,
            "sources": [],
            "confidence": 1.0,
            "published_report": f"{explanation} {clarifying_question}",
        }
    ).model_dump()

    return {
        "final_report": final_report,
        "messages": [AIMessage(content=explanation)],
    }


def _chunk_text(text: str, *, max_chars: int = 520, overlap: int = 80) -> list[str]:
    """Split long text into overlapping, sentence-friendly chunks."""

    compact = _compact_whitespace(text)
    if not compact:
        return []
    if len(compact) <= max_chars:
        return [compact]

    chunks: list[str] = []
    start = 0
    text_length = len(compact)
    while start < text_length:
        end = min(start + max_chars, text_length)
        if end < text_length:
            boundary = compact.rfind(". ", start, end)
            if boundary == -1:
                boundary = compact.rfind(" ", start, end)
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = compact[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(0, end - overlap)
    return chunks


def _truncate_summary(value: Any, limit: int = SUMMARY_CHAR_LIMIT) -> str:
    """Return a compact summary capped to the requested character limit."""

    text = _compact_whitespace(str(value or ""))
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _normalize_sources(value: Any) -> list[dict[str, str]]:
    """Coerce model-produced sources into a predictable list of title/url records."""

    if not isinstance(value, list):
        return []

    normalized_sources: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            normalized_sources.append(
                {
                    "title": str(item.get("title") or "Untitled source"),
                    "url": str(item.get("url") or ""),
                }
            )
            continue

        if isinstance(item, str) and item.strip():
            normalized_sources.append(
                {
                    "title": item.strip(),
                    "url": "",
                }
            )

    return normalized_sources


def _source_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    """Build a stable source identity for diversity scoring and source caps."""

    url = str(item.get("url", "")).strip().lower()
    title = _compact_whitespace(str(item.get("title", "")).strip().lower())
    tool_name = str(item.get("tool_name", "")).strip().lower()
    return (url, title, tool_name)


def _normalize_draft_report(draft_report: dict[str, Any], question: str) -> dict[str, Any]:
    """Enforce a consistent draft schema before handing it to the review gate."""

    normalized_findings = [
        _compact_whitespace(str(item))
        for item in draft_report.get("findings") or []
        if _compact_whitespace(str(item))
    ][:5]
    fallback_findings = [
        "Evidence coverage is still narrow and should be reviewed before publication.",
        "At least one independent source corroborates part of the answer.",
        "Important tradeoffs and unknowns are captured in the final summary.",
    ]
    while len(normalized_findings) < 3:
        normalized_findings.append(fallback_findings[len(normalized_findings)])

    normalized = {
        "title": draft_report.get("title") or f"Research Report: {question}",
        "findings": normalized_findings,
        "sources": _normalize_sources(draft_report.get("sources")),
        "confidence": _clamp(float(draft_report.get("confidence", 0.5) or 0.5)),
        "summary": _truncate_summary(draft_report.get("summary", "")),
    }
    return DraftReportModel.model_validate(normalized).model_dump()


def _resolve_relevant_history(
    past_topics: list[dict[str, Any]],
    raw_relevant_history: Any,
) -> list[dict[str, Any]]:
    """Map model-selected history hints back to the original stored records."""

    if not isinstance(raw_relevant_history, list):
        return []

    by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    for item in sort_history_records(past_topics):
        question = str(item.get("question", "")).strip()
        created_at = str(item.get("created_at", "")).strip()
        by_identity[(question, created_at)] = item

    resolved: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in raw_relevant_history:
        if not isinstance(candidate, dict):
            continue

        question = str(candidate.get("question", "")).strip()
        created_at = str(candidate.get("created_at", "")).strip()
        matched_item = by_identity.get((question, created_at))
        if matched_item is None and question:
            matched_item = _find_newest_exact_history_match(question, past_topics)
        if matched_item is None:
            continue

        identity = (
            str(matched_item.get("question", "")).strip(),
            str(matched_item.get("created_at", "")).strip(),
        )
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(matched_item)

    return resolved[:3]


def _lexical_overlap_score(question: str, content: str) -> float:
    """Cheap lexical fallback for retrieval when embeddings are unavailable."""

    question_terms = {term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) > 2}
    content_terms = {term for term in re.findall(r"[a-z0-9]+", content.lower()) if len(term) > 2}
    if not question_terms or not content_terms:
        return 0.0
    overlap = len(question_terms & content_terms)
    return overlap / max(len(question_terms), 1)


def _title_overlap_score(question: str, title: str) -> float:
    """Score how much the query overlaps with the result title."""

    return _lexical_overlap_score(question, title)


def _history_terms(value: str) -> set[str]:
    tokens = [
        term
        for term in re.findall(r"[a-z0-9]+", value.lower())
        if len(term) > 1 and term not in HISTORY_STOPWORDS
    ]

    normalized_terms: list[str] = []
    for term in tokens:
        normalized = term
        if normalized.endswith("ies") and len(normalized) > 4:
            normalized = normalized[:-3] + "y"
        elif normalized.endswith("sses") and len(normalized) > 5:
            normalized = normalized[:-2]
        elif normalized.endswith("s") and not normalized.endswith("ss") and len(normalized) > 3:
            normalized = normalized[:-1]
        if normalized and normalized not in HISTORY_STOPWORDS:
            normalized_terms.append(normalized)

    terms = set(normalized_terms)
    for left, right in zip(normalized_terms, normalized_terms[1:]):
        phrase = f"{left} {right}"
        if len(phrase) > 3:
            terms.add(phrase)
    return terms


def _history_question_key(value: str) -> str:
    """Normalize a question so exact reuse only matches the same wording."""

    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _find_newest_exact_history_match(question: str, history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the newest stored record whose question matches exactly after normalization."""

    question_key = _history_question_key(question)
    if not question_key:
        return None

    for item in sort_history_records(history):
        if _history_question_key(str(item.get("question", ""))) == question_key:
            return item
    return None


def _history_relevance_score(question: str, item: dict[str, Any]) -> float:
    """Score whether a stored history record is close enough to the current question."""

    current_terms = _history_terms(question)
    item_question = str(item.get("question", "")).strip()
    report = item.get("report", {})
    item_text = " ".join(
        str(part or "")
        for part in [
            item_question,
            report.get("title", ""),
            report.get("summary", ""),
        ]
    )
    item_terms = _history_terms(item_text)

    if not current_terms or not item_terms:
        return 0.0

    if _compact_whitespace(question).lower() == _compact_whitespace(item_question).lower():
        return 1.0

    overlap = len(current_terms & item_terms)
    if overlap == 0:
        return 0.0

    precision = overlap / max(len(item_terms), 1)
    recall = overlap / max(len(current_terms), 1)
    if precision + recall == 0:
        return 0.0

    score = (2 * precision * recall) / (precision + recall)
    if overlap >= 5:
        score = max(score, 0.82)
    elif overlap >= 4:
        score = max(score, 0.72)
    elif overlap >= 3:
        score = max(score, 0.58)
    elif overlap >= 2:
        score = max(score, 0.42)

    strong_shared_terms = {
        term for term in current_terms & item_terms
        if len(term) >= 5
        and term not in {"process", "processing", "understanding", "context", "question", "answer", "research", "study"}
    }
    if strong_shared_terms:
        score = max(score, 0.6)

    return min(1.0, score)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for two embedding vectors."""

    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _embed_texts(embeddings, texts: list[str]) -> list[list[float]]:
    """Return embeddings, falling back to an empty list when unavailable."""

    if embeddings is None or not texts:
        return []
    try:
        return embeddings.embed_documents(texts)
    except Exception:
        return []


def _reciprocal_rank_fusion(rank_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    """Combine multiple ranked lists into one robust fusion score."""

    fused_scores: dict[int, float] = {}
    for ranked_indexes in rank_lists:
        for rank, index in enumerate(ranked_indexes, start=1):
            fused_scores[index] = fused_scores.get(index, 0.0) + (1.0 / (k + rank))
    return fused_scores


def _rank_indexes_desc(scores: list[float]) -> list[int]:
    """Return item indexes sorted by descending score."""

    return sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)


def _diversity_rerank(items: list[dict[str, Any]], *, query: str, limit: int) -> list[dict[str, Any]]:
    """Promote relevance while limiting redundant chunks from the same source or tool."""

    if not items:
        return []

    title_scores = [_title_overlap_score(query, str(item.get("title", ""))) for item in items]
    snippet_scores = [_lexical_overlap_score(query, str(item.get("snippet", ""))) for item in items]
    base_scores = [float(item.get("score", 0.0)) for item in items]
    fused_scores = _reciprocal_rank_fusion(
        [
            _rank_indexes_desc(base_scores),
            _rank_indexes_desc(title_scores),
            _rank_indexes_desc(snippet_scores),
        ]
    )

    selected: list[dict[str, Any]] = []
    selected_indexes: set[int] = set()
    source_counts: dict[tuple[str, str, str], int] = {}
    tool_counts: dict[str, int] = {}

    while len(selected) < min(limit, len(items)):
        best_index = -1
        best_score = -1.0
        for index, item in enumerate(items):
            if index in selected_indexes:
                continue

            source_identity = _source_identity(item)
            tool_name = str(item.get("tool_name", "")).strip().lower()
            duplicate_penalty = 0.14 * source_counts.get(source_identity, 0)
            tool_penalty = 0.05 * tool_counts.get(tool_name, 0)

            mmr_penalty = 0.0
            for chosen in selected:
                mmr_penalty = max(
                    mmr_penalty,
                    max(
                        _lexical_overlap_score(str(item.get("snippet", "")), str(chosen.get("snippet", ""))),
                        _title_overlap_score(str(item.get("title", "")), str(chosen.get("title", ""))),
                    ),
                )

            candidate_score = fused_scores.get(index, 0.0) - duplicate_penalty - tool_penalty - (0.12 * mmr_penalty)
            if candidate_score > best_score:
                best_score = candidate_score
                best_index = index

        if best_index == -1:
            break

        chosen_item = dict(items[best_index])
        chosen_item["score"] = round(
            _clamp((0.7 * float(chosen_item.get("score", 0.0))) + (0.3 * min(1.0, fused_scores.get(best_index, 0.0) * 25))),
            4,
        )
        selected.append(chosen_item)
        selected_indexes.add(best_index)

        source_identity = _source_identity(chosen_item)
        tool_name = str(chosen_item.get("tool_name", "")).strip().lower()
        source_counts[source_identity] = source_counts.get(source_identity, 0) + 1
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

    return selected


def _score_history_chunks(
    question: str,
    past_topics: list[dict[str, Any]],
    *,
    embeddings=None,
) -> tuple[list[dict[str, Any]], str, dict[str, int]]:
    """Retrieve the most relevant history chunks using hybrid lexical and embedding scoring."""

    candidates: list[dict[str, Any]] = []
    for item in past_topics:
        history_score = _history_relevance_score(question, item)
        if history_score < MIN_HISTORY_RELEVANCE_SCORE:
            continue

        report = item.get("report", {})
        combined_text = "\n".join(
            part
            for part in [
                item.get("question", ""),
                report.get("title", ""),
                report.get("summary", ""),
                report.get("published_report", ""),
            ]
            if part
        )
        for index, chunk in enumerate(_chunk_text(combined_text, max_chars=460, overlap=60)):
            candidates.append(
                {
                    "tool_name": "history_memory",
                    "title": report.get("title") or item.get("question") or "Prior research",
                    "url": "",
                    "snippet": chunk[:EVIDENCE_SNIPPET_LIMIT],
                    "score": 0.0,
                    "source_type": "history_memory",
                    "chunk_id": f"history-{item.get('created_at', 'na')}-{index}",
                    "question": item.get("question", ""),
                    "created_at": item.get("created_at", ""),
                    "history_relevance": round(history_score, 4),
                }
            )

    if not candidates:
        return [], "lexical", {
            "rerank_applied": 0,
            "rerank_candidates": 0,
            "rerank_duplicates_removed": 0,
            "rerank_trimmed_for_limit": 0,
            "rerank_distinct_sources": 0,
        }

    lexical_scores = [_lexical_overlap_score(question, item["snippet"]) for item in candidates]
    embedding_scores = [0.0] * len(candidates)
    strategy = "lexical"

    if embeddings is not None and len(candidates) > MAX_HISTORY_CHUNKS:
        chunk_embeddings = _embed_texts(embeddings, [item["snippet"] for item in candidates])
    else:
        chunk_embeddings = []

    if chunk_embeddings:
        try:
            question_embedding = embeddings.embed_query(question)
            embedding_scores = [_cosine_similarity(question_embedding, vector) for vector in chunk_embeddings]
            strategy = "hybrid-embedding"
        except Exception:
            embedding_scores = [0.0] * len(candidates)

    ranked: list[dict[str, Any]] = []
    for item, lexical_score, embedding_score in zip(candidates, lexical_scores, embedding_scores):
        combined_score = _clamp((0.45 * lexical_score) + (0.55 * max(0.0, embedding_score)))
        enriched = dict(item)
        enriched["score"] = round(combined_score, 4)
        ranked.append(enriched)

    reranked = _diversity_rerank(ranked, query=question, limit=MAX_HISTORY_CHUNKS)
    return reranked, strategy if strategy != "lexical" else "hybrid-rrf", {
        "rerank_applied": 1,
        "rerank_candidates": len(ranked),
        "rerank_duplicates_removed": 0,
        "rerank_trimmed_for_limit": max(0, len(ranked) - len(reranked)),
        "rerank_distinct_sources": len({_source_identity(item) for item in reranked}),
    }


def _coerce_tool_payload(content: Any) -> Any:
    """Best-effort coercion of tool output into structured Python values."""

    if isinstance(content, (list, dict)):
        return content
    if not isinstance(content, str):
        return content
    text = content.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except Exception:
            continue
    return text


def _normalize_tool_results(tool_name: str, payload: Any) -> list[dict[str, Any]]:
    """Convert raw tool payloads into normalized evidence items."""

    normalized_results: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        embedded_results = payload.get("results")
        if isinstance(embedded_results, list):
            normalized_results.extend(_normalize_tool_results(tool_name, embedded_results))

        answer = payload.get("answer")
        if isinstance(answer, str) and answer.strip():
            normalized_results.extend(
                [
                    {
                        "tool_name": tool_name,
                        "title": f"{tool_name.replace('_', ' ').title()} answer",
                        "url": "",
                        "snippet": _compact_whitespace(answer)[:EVIDENCE_SNIPPET_LIMIT],
                        "score": 0.61,
                        "source_type": "tool_summary",
                        "chunk_id": f"{tool_name}-answer-0",
                    }
                ]
            )

        return normalized_results

    if isinstance(payload, list):
        for item_index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            title = _compact_whitespace(
                str(
                    item.get("title")
                    or item.get("source")
                    or item.get("url")
                    or f"{tool_name} result {item_index + 1}"
                )
            )
            url = str(item.get("url") or item.get("source") or "")
            raw_text = item.get("content") or item.get("raw_content") or item.get("answer") or ""
            for chunk_index, chunk in enumerate(_chunk_text(str(raw_text), max_chars=500, overlap=70)[:2]):
                normalized_results.append(
                    {
                        "tool_name": tool_name,
                        "title": title or tool_name,
                        "url": url,
                        "snippet": chunk[:EVIDENCE_SNIPPET_LIMIT],
                        "score": _clamp(float(item.get("score") or 0.72) - (chunk_index * 0.04)),
                        "source_type": "web_search",
                        "chunk_id": f"{tool_name}-{item_index}-{chunk_index}",
                    }
                )
        return normalized_results

    text_payload = _compact_whitespace(str(payload or ""))
    if not text_payload:
        return []

    for chunk_index, chunk in enumerate(_chunk_text(text_payload, max_chars=500, overlap=70)[:2]):
        normalized_results.append(
            {
                "tool_name": tool_name,
                "title": tool_name.replace("_", " ").title(),
                "url": "",
                "snippet": chunk[:EVIDENCE_SNIPPET_LIMIT],
                "score": _clamp(0.66 - (chunk_index * 0.04)),
                "source_type": "reference",
                "chunk_id": f"{tool_name}-text-{chunk_index}",
            }
        )

    return normalized_results


def _dedupe_evidence(items: list[dict[str, Any]], *, query: str = "") -> list[dict[str, Any]]:
    """Remove duplicate evidence entries, then rerank for relevance and source diversity."""

    best_by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        identity = (
            str(item.get("title", "")).strip().lower(),
            str(item.get("url", "")).strip().lower(),
            str(item.get("snippet", "")).strip().lower(),
        )
        current = best_by_identity.get(identity)
        if current is None or float(item.get("score", 0.0)) > float(current.get("score", 0.0)):
            best_by_identity[identity] = item
    deduped = list(best_by_identity.values())

    if query.strip() and len(deduped) > 4:
        deduped = _diversity_rerank(deduped, query=query, limit=len(deduped))
    else:
        deduped.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)

    limited_results: list[dict[str, Any]] = []
    source_counts: dict[tuple[str, str, str], int] = {}
    for item in deduped:
        source_identity = _source_identity(item)
        if source_counts.get(source_identity, 0) >= MAX_CHUNKS_PER_SOURCE:
            continue
        source_counts[source_identity] = source_counts.get(source_identity, 0) + 1
        limited_results.append(item)
        if len(limited_results) >= MAX_EVIDENCE_ITEMS:
            break

    return limited_results


def _summarize_rerank_metrics(raw_count: int, deduped_count: int, final_items: list[dict[str, Any]], *, rerank_applied: bool) -> dict[str, int]:
    """Summarize telemetry for rerank monitoring."""

    return {
        "rerank_applied": 1 if rerank_applied else 0,
        "rerank_candidates": raw_count,
        "rerank_duplicates_removed": max(0, raw_count - deduped_count),
        "rerank_trimmed_for_limit": max(0, deduped_count - len(final_items)),
        "rerank_distinct_sources": len({_source_identity(item) for item in final_items}) if final_items else 0,
    }


def _summarize_evidence(items: list[dict[str, Any]]) -> str:
    """Format top evidence items into a concise text digest for prompts."""

    lines = []
    for item in items[:6]:
        title = item.get("title", "Untitled source")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        score = float(item.get("score", 0.0))
        source_type = item.get("source_type", "evidence")
        url_text = f" ({url})" if url else ""
        lines.append(f"- [{source_type} | {score:.2f}] {title}{url_text}: {snippet}")
    return "\n".join(lines) if lines else "No evidence captured yet."


def _select_evidence_by_ids(items: list[dict[str, Any]], selected_ids: list[str]) -> list[dict[str, Any]]:
    """Return the selected evidence items in the order they appeared in the board."""

    if not selected_ids:
        return []

    wanted = {str(item).strip() for item in selected_ids if str(item).strip()}
    if not wanted:
        return []

    selected: list[dict[str, Any]] = []
    for item in items:
        chunk_id = str(item.get("chunk_id", "")).strip()
        if chunk_id and chunk_id in wanted:
            selected.append(item)
    return selected


def _build_metrics(
    state: ResearchState,
    *,
    retrieval_strategy: str | None = None,
    history_candidates: int | None = None,
    rerank_metrics: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Update run metrics without losing previously captured values."""

    current = dict(state.get("run_metrics", {}))
    evidence_items = len(state.get("search_results", []))
    unique_sources = len(
        {
            _source_identity(item)
            for item in state.get("search_results", [])
        }
    )
    current.update(
        {
            "iterations_used": int(state.get("iteration", current.get("iterations_used", 0)) or 0),
            "evidence_items": evidence_items,
            "unique_sources": unique_sources,
            "history_candidates": history_candidates
            if history_candidates is not None
            else int(current.get("history_candidates", len(state.get("retrieval_context", []))) or 0),
            "retrieval_strategy": retrieval_strategy or current.get("retrieval_strategy", "lexical"),
            "rerank_applied": int((rerank_metrics or {}).get("rerank_applied", current.get("rerank_applied", 0)) or 0),
            "rerank_candidates": int((rerank_metrics or {}).get("rerank_candidates", current.get("rerank_candidates", 0)) or 0),
            "rerank_duplicates_removed": int((rerank_metrics or {}).get("rerank_duplicates_removed", current.get("rerank_duplicates_removed", 0)) or 0),
            "rerank_trimmed_for_limit": int((rerank_metrics or {}).get("rerank_trimmed_for_limit", current.get("rerank_trimmed_for_limit", 0)) or 0),
            "rerank_distinct_sources": int((rerank_metrics or {}).get("rerank_distinct_sources", current.get("rerank_distinct_sources", 0)) or 0),
        }
    )
    return current


def initialize_run_node(state: ResearchState) -> dict[str, Any]:
    """Initialize fresh run-scoped state before loading shared history."""

    sanitized_question = _sanitize_question(state.get("question", ""))
    guardrails = _assess_question(sanitized_question)

    return {
        "question": sanitized_question,
        "search_results": [],
        "retrieval_context": [],
        "iteration": 0,
        "reasoner_decision": "",
        "history_review": {
            "match_type": "new",
            "rationale": "",
            "relevant_history": [],
        },
        "research_plan": [],
        "guardrails": guardrails,
        "run_metrics": {
            "iterations_used": 0,
            "evidence_items": 0,
            "unique_sources": 0,
            "history_candidates": 0,
            "retrieval_strategy": "lexical",
            "rerank_applied": 0,
            "rerank_candidates": 0,
            "rerank_duplicates_removed": 0,
            "rerank_trimmed_for_limit": 0,
            "rerank_distinct_sources": 0,
        },
        "history_decision": "",
        "reused_topic": None,
        "draft_report": None,
        "final_report": None,
        "selected_evidence_ids": [],
        "selected_evidence": [],
        "human_feedback": "",
        "review_decision": "",
    }


def load_history_node(state: ResearchState, *, store: BaseStore) -> dict[str, Any]:
    """Load shared published research history into the current run."""

    namespace = ("research_history", "shared")
    existing = store.get(namespace, "past_topics")
    in_memory_history = existing.value if existing else []
    persisted_history = load_persisted_history()
    history = sort_history_records(merge_history_records(persisted_history, in_memory_history))

    if history != in_memory_history:
        store.put(namespace, "past_topics", history)

    return {
        "past_topics": history,
    }


def history_review_node(state: ResearchState, *, llm, embeddings=None) -> dict[str, Any]:
    """Assess whether prior published work is similar, related, or new."""

    past_topics = state.get("past_topics", [])
    retrieved_history, retrieval_strategy, rerank_metrics = _score_history_chunks(
        state["question"],
        past_topics,
        embeddings=embeddings,
    )

    if not past_topics:
        return {
            "history_review": {
                "match_type": "new",
                "rationale": "No prior published research records were available.",
                "relevant_history": [],
            },
            "retrieval_context": [],
            "run_metrics": _build_metrics(state, retrieval_strategy=retrieval_strategy, history_candidates=0, rerank_metrics=rerank_metrics),
        }

    eligible_history = [item for item in past_topics if _history_relevance_score(state["question"], item) >= MIN_HISTORY_RELEVANCE_SCORE]
    exact_reuse_candidate = _find_newest_exact_history_match(state["question"], past_topics)

    if exact_reuse_candidate is not None:
        match_type = "similar"
        rationale = "Found an exact prior question match, so the current run can reuse the closest prior context."
        relevant_history = [exact_reuse_candidate]
    else:
        match_type = "new"
        rationale = "No exact prior question match was found, so this run will start fresh without reusing prior history."
        relevant_history = []

    relevant_history = _resolve_relevant_history(
        eligible_history,
        [
            {
                "question": item.get("question", ""),
                "created_at": item.get("created_at", ""),
            }
            for item in relevant_history
        ],
    )
    if match_type in {"similar", "related"} and not relevant_history:
        match_type = "new"
        rationale = "No prior research record was similar enough to reuse."

    return {
        "history_review": {
            "match_type": match_type,
            "rationale": rationale,
            "relevant_history": relevant_history[:3],
        },
        "retrieval_context": retrieved_history if match_type == "similar" else [],
        "run_metrics": _build_metrics(
            state,
            retrieval_strategy=retrieval_strategy,
            history_candidates=len(retrieved_history) if match_type == "similar" else 0,
            rerank_metrics=rerank_metrics,
        ),
    }


def history_review_gate_node(state: ResearchState) -> dict[str, Any]:
    """Pause for user review when prior published work looks similar or related."""

    history_review = state.get("history_review", {})
    match_type = history_review.get("match_type", "new")
    relevant_history = history_review.get("relevant_history", [])
    reuse_candidate = _find_newest_exact_history_match(state["question"], state.get("past_topics", []))

    if match_type == "new" or not relevant_history or reuse_candidate is None:
        return {"history_decision": "proceed_with_context"}

    matches = []
    for item in relevant_history:
        report = item.get("report", {})
        matches.append(
            {
                "question": item.get("question", ""),
                "published_report": report.get("published_report", ""),
                "title": report.get("title", ""),
                "summary": report.get("summary", ""),
                "user_id": item.get("user_id", ""),
                "created_at": item.get("created_at", ""),
            }
        )

    decision = interrupt(
        {
            "action": "review_history_match",
            "current_question": state["question"],
            "match_type": match_type,
            "rationale": history_review.get("rationale", ""),
            "matches": matches,
            "reuse_allowed": bool(reuse_candidate),
            "reuse_candidate": (
                {
                    "question": reuse_candidate.get("question", ""),
                    "published_report": reuse_candidate.get("report", {}).get("published_report", ""),
                    "title": reuse_candidate.get("report", {}).get("title", ""),
                    "summary": reuse_candidate.get("report", {}).get("summary", ""),
                    "user_id": reuse_candidate.get("user_id", ""),
                    "created_at": reuse_candidate.get("created_at", ""),
                }
                if reuse_candidate
                else None
            ),
        }
    )

    if isinstance(decision, str):
        return {"history_decision": decision}

    if isinstance(decision, dict):
        return {
            "history_decision": decision.get("resume")
            or decision.get("action")
            or decision.get("decision")
            or "",
        }

    return {"history_decision": str(decision)}


def route_after_history_review_gate(state: ResearchState) -> str:
    """Route based on the user's decision after reviewing prior history."""

    decision = state.get("history_decision", "proceed_with_context")
    reuse_candidate = _find_newest_exact_history_match(state["question"], state.get("past_topics", []))
    if decision == "start_fresh_plan":
        return "start_fresh_plan"
    if decision == "reuse_existing" and reuse_candidate is not None:
        return "reuse_existing"
    return "proceed_with_context"


def reuse_existing_report_node(state: ResearchState) -> dict[str, Any]:
    """Reuse the best matched prior published report without new research."""

    reuse_candidate = _find_newest_exact_history_match(state["question"], state.get("past_topics", []))
    if reuse_candidate is None:
        return {"history_decision": "proceed_with_context"}

    reused_report = reuse_candidate.get("report", {})

    return {
        "reused_topic": reuse_candidate,
        "final_report": reused_report,
        "messages": [
            AIMessage(
                content=(
                    "Reused the newest exact-match published report from history for the current question."
                )
            )
        ],
    }


def planner_node(state: ResearchState, *, llm) -> dict[str, Any]:
    """Create a lightweight plan without spending an extra model call."""

    history_review = state.get("history_review", {})
    use_history = state.get("history_decision", "proceed_with_context") != "start_fresh_plan"
    force_fresh_replan = state.get("review_decision", "") == "rejected"
    relevant_history = history_review.get("relevant_history", []) if use_history else []
    guardrails = state.get("guardrails", {})

    if force_fresh_replan:
        relevant_history = []

    research_plan = _build_local_research_plan(state["question"], guardrails, relevant_history)
    content = "\n".join(f"- {query}" for query in research_plan)

    update: dict[str, Any] = {"messages": [AIMessage(content=content)], "research_plan": research_plan}
    if force_fresh_replan:
        update.update(
            {
                "search_results": [],
                "retrieval_context": [],
                "selected_evidence_ids": [],
                "selected_evidence": [],
                "iteration": 0,
                "reasoner_decision": "",
                "draft_report": None,
                "final_report": None,
            }
        )
    return update


def prepare_search_node(state: ResearchState) -> dict[str, Any]:
    """Advance the loop counter before another search round begins."""

    next_iteration = state.get("iteration", 0) + 1
    return {"iteration": next_iteration}


def capture_tool_results_node(state: ResearchState, config) -> dict[str, Any]:
    """Store normalized tool responses for downstream reasoning and synthesis."""

    configurable = config.get("configurable", {})
    excerpt_limit = configurable.get("tool_excerpt_chars", 1200)

    latest_results: list[dict[str, Any]] = []
    for message in reversed(state.get("messages", [])):
        if not isinstance(message, ToolMessage):
            if latest_results:
                break
            continue

        raw_content = message.content
        payload = _coerce_tool_payload(raw_content)
        excerpt = _truncate_text(raw_content, excerpt_limit)
        message.content = excerpt
        latest_results.extend(
            _normalize_tool_results(
                getattr(message, "name", "unknown_tool"),
                payload,
            )
        )

    merged_input = state.get("search_results", []) + list(reversed(latest_results))
    merged_results = _dedupe_evidence(
        merged_input,
        query=state.get("question", ""),
    )
    rerank_metrics = _summarize_rerank_metrics(
        len(merged_input),
        len({
            (
                str(item.get("title", "")).strip().lower(),
                str(item.get("url", "")).strip().lower(),
                str(item.get("snippet", "")).strip().lower(),
            )
            for item in merged_input
        }),
        merged_results,
        rerank_applied=bool(state.get("question", "").strip()),
    )

    next_state = dict(state)
    next_state["search_results"] = merged_results
    return {
        "search_results": merged_results,
        "run_metrics": _build_metrics(next_state, rerank_metrics=rerank_metrics),
    }


def reason_node(state: ResearchState, *, llm) -> dict[str, Any]:
    """Decide whether more research is needed or synthesis can begin."""

    iteration = int(state.get("iteration", 0) or 0)
    max_iterations = int(state.get("max_iterations", 3) or 3)

    reasoner_decision, reason = _decide_reasoner_locally(state)
    if iteration >= max_iterations:
        reasoner_decision = "DONE"
        reason = f"The loop guard has been reached at iteration {iteration}."

    content = f"{reasoner_decision}: {reason}"
    return {"messages": [AIMessage(content=content)], "reasoner_decision": reasoner_decision}


def route_after_reason(state: ResearchState) -> str:
    """Route either back into the search loop or forward to synthesis."""

    if state.get("reasoner_decision", "").upper() == "DONE":
        if state.get("search_results"):
            return "evidence_selection_gate_node"
        return "synthesise_node"

    return "prepare_search_node"


def evidence_selection_gate_node(state: ResearchState) -> dict[str, Any]:
    """Pause so the user can choose which evidence should drive the report."""

    evidence = list(state.get("search_results", []))[:8]
    if not evidence:
        return {
            "selected_evidence_ids": [],
            "selected_evidence": [],
        }

    decision = interrupt(
        {
            "action": "select_evidence_for_report",
            "question": state["question"],
            "research_plan": list(state.get("research_plan", [])),
            "current_evidence": evidence,
            "instructions": (
                "Select one or more evidence items to use for the report. "
                "The report synthesis step will use only the selected evidence."
            ),
        }
    )

    selected_ids: list[str] = []
    if isinstance(decision, dict):
        raw_ids = (
            decision.get("selected_evidence_ids")
            or decision.get("selectedEvidenceIds")
            or decision.get("selected_chunk_ids")
            or decision.get("selected_chunk_id")
            or decision.get("selected_evidence")
            or []
        )
        if isinstance(raw_ids, list):
            for item in raw_ids:
                if isinstance(item, dict):
                    candidate = str(item.get("chunk_id", "")).strip() or str(item.get("title", "")).strip()
                else:
                    candidate = str(item).strip()
                if candidate:
                    selected_ids.append(candidate)
        elif isinstance(raw_ids, str) and raw_ids.strip():
            selected_ids = [raw_ids.strip()]

    selected_evidence = _select_evidence_by_ids(evidence, selected_ids)
    if not selected_evidence:
        selected_evidence = evidence[:1]
        selected_ids = [str(item.get("chunk_id", "")).strip() for item in selected_evidence if str(item.get("chunk_id", "")).strip()]

    return {
        "selected_evidence_ids": selected_ids,
        "selected_evidence": selected_evidence,
    }


def synthesise_node(state: ResearchState, *, llm) -> dict[str, Any]:
    """Turn the gathered research context into a structured draft report."""

    search_results = (state.get("selected_evidence") or state.get("search_results", []))[:MAX_SEARCH_RESULTS_FOR_PROMPT]
    retrieved_history = state.get("retrieval_context", [])

    prompt = [
        SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research question: {state['question']}\n\n"
                f"Question guardrails: {json.dumps({k: state.get('guardrails', {}).get(k) for k in ('status', 'recommended_action', 'allowed_tools', 'risk_flags')}, default=str)}\n\n"
                f"Research plan: {json.dumps(state.get('research_plan', [])[:3], default=str)}\n\n"
                f"Selected evidence:\n{_summarize_evidence(search_results)}\n\n"
                f"Relevant history:\n{_summarize_evidence(retrieved_history[:MAX_HISTORY_ITEMS_FOR_PROMPT])}\n\n"
                f"Return valid JSON with keys: title, findings, sources, confidence, summary. "
                f"Keep summary under {SUMMARY_CHAR_LIMIT} characters."
            )
        ),
    ]

    try:
        draft_report = llm.with_structured_output(DraftReportModel).invoke(prompt).model_dump()
    except Exception:
        response = llm.invoke(prompt)
        draft_report = {
            "title": f"Research Report: {state['question']}",
            "findings": [
                "Could not fully parse structured output. Review the draft carefully.",
                "Search evidence was still captured for manual review.",
                "Use the cited sources to confirm key claims before publishing.",
            ],
            "sources": [],
            "confidence": 0.5,
            "summary": response.content,
        }

    draft_report = _normalize_draft_report(draft_report, state["question"])
    if not draft_report["sources"]:
        draft_report["sources"] = [
            {"title": item.get("title", "Untitled source"), "url": item.get("url", "")}
            for item in search_results[:4]
        ]
        draft_report = DraftReportModel.model_validate(draft_report).model_dump()

    next_state = dict(state)
    next_state["draft_report"] = draft_report
    return {
        "draft_report": draft_report,
        "run_metrics": _build_metrics(next_state),
        "messages": [
            AIMessage(content=f"Draft report prepared.\n{json.dumps(draft_report, indent=2)}")
        ],
    }


def review_gate_node(state: ResearchState):
    """Pause for human review before publishing the report."""

    decision = interrupt(
        {
            "action": "review_before_publish",
            "question": state["question"],
            "iterations": state.get("iteration", 0),
            "draft": state["draft_report"],
        }
    )

    if isinstance(decision, str):
        return {"review_decision": decision}

    if isinstance(decision, dict):
        review_decision = decision.get("resume") or decision.get("action") or decision.get("decision") or ""
        feedback = decision.get("human_feedback") or decision.get("feedback")
        if feedback is not None:
            feedback_text = str(feedback)
        else:
            feedback_text = ""

        if review_decision == "approved" and feedback_text.strip():
            review_decision = "edited"

        update = {
            "review_decision": review_decision,
        }
        if feedback_text:
            update["human_feedback"] = feedback_text
        return update

    return {"review_decision": str(decision)}


def apply_edit_node(state: ResearchState) -> dict[str, Any]:
    """Apply reviewer feedback to the draft report before publishing."""

    feedback = state.get("human_feedback", "").strip()
    draft_report = dict(state["draft_report"])

    if feedback:
        draft_report["summary"] = _truncate_summary(
            f"{draft_report.get('summary', '')}\n\nReviewer note: {feedback}"
        )

    return {"draft_report": DraftReportModel.model_validate(draft_report).model_dump()}


def publish_node(state: ResearchState, *, llm) -> dict[str, Any]:
    """Produce the final polished user-facing report."""

    draft_report = state["draft_report"]
    published_report = _format_final_report(draft_report, state["question"], state.get("human_feedback", ""))
    final_report = FinalReportModel.model_validate(
        {
            "title": draft_report.get("title", f"Research Report: {state['question']}"),
            "summary": _truncate_summary(draft_report.get("summary", "")),
            "key_findings": list(draft_report.get("findings", [])),
            "sources": _normalize_sources(draft_report.get("sources", [])),
            "confidence": float(draft_report.get("confidence", 0.5)),
            "published_report": published_report,
        }
    ).model_dump()

    next_state = dict(state)
    next_state["final_report"] = final_report
    return {
        "final_report": final_report,
        "run_metrics": _build_metrics(next_state),
        "messages": [AIMessage(content=published_report)],
    }


def save_history_node(state: ResearchState, *, store: BaseStore) -> dict[str, Any]:
    """Persist the completed question and published report in shared memory."""

    namespace = ("research_history", "shared")
    existing = store.get(namespace, "past_topics")
    history = existing.value if existing else []

    if state.get("reused_topic"):
        return {}

    if not state.get("final_report"):
        return {}

    history.append(
        {
            "question": state["question"],
            "report": state["final_report"],
            "user_id": state["user_id"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )

    merged_history = merge_history_records(load_persisted_history(), history)
    store.put(namespace, "past_topics", merged_history)
    save_persisted_history(merged_history)
    return {}
