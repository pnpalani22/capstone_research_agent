from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from deep_translator import GoogleTranslator
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import (
    build_run_config,
    create_research_app,
    get_pending_interrupt,
    get_run_state,
    resume_research_run,
    start_research_run,
)
from schemas import (
    CreateSessionResponse,
    EvidenceSelectionInterruptModel,
    HistoryInterruptModel,
    ResumeResearchRequest,
    ReviewInterruptModel,
    RunSnapshotResponse,
    StartResearchRequest,
    TranslateTextRequest,
    TranslateTextResponse,
)
from error_utils import friendly_api_error_message, friendly_token_exhaustion_message, is_token_exhaustion_error


research_app = create_research_app()
logger = logging.getLogger(__name__)
error_log_path = Path(__file__).with_name("backend_errors.log")

if not logger.handlers:
    logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(error_log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)
    logger.propagate = True

api = FastAPI(title="Deep Research Agent API", version="1.0.0")

api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _config_for_thread(thread_id: str) -> dict[str, object]:
    return build_run_config(thread_id)


def _raise_run_error(exc: Exception, context: str) -> None:
    if is_token_exhaustion_error(exc):
        logger.exception("%s stopped because the API quota or token limit was reached.", context, exc_info=exc)
        raise HTTPException(status_code=503, detail=friendly_token_exhaustion_message(context)) from exc
    logger.exception("%s failed unexpectedly.", context, exc_info=exc)
    raise HTTPException(status_code=500, detail=friendly_api_error_message(exc, context)) from exc


@api.exception_handler(Exception)
def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
    """Return a friendly error payload for any unhandled backend failure."""

    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if is_token_exhaustion_error(exc):
        logger.exception("Unhandled token exhaustion error in the research API.", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"detail": friendly_token_exhaustion_message("The research run")},
        )

    logger.exception("Unhandled exception in the research API.", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": friendly_api_error_message(exc, "The research run")},
    )


def _snapshot_for_thread(thread_id: str) -> RunSnapshotResponse:
    config = _config_for_thread(thread_id)
    state = get_run_state(research_app, config)
    interrupt_payload = get_pending_interrupt(research_app, config)

    interrupt = None
    status = "idle"

    if interrupt_payload:
        action = interrupt_payload.get("action")
        if action == "review_history_match":
            interrupt = HistoryInterruptModel.model_validate(interrupt_payload)
        elif action == "select_evidence_for_report":
            interrupt = EvidenceSelectionInterruptModel.model_validate(interrupt_payload)
        elif action == "review_before_publish":
            interrupt = ReviewInterruptModel.model_validate(interrupt_payload)
        status = "waiting_input"
    elif state.get("final_report"):
        status = "completed"

    return RunSnapshotResponse(
        thread_id=thread_id,
        status=status,
        question=str(state.get("question", "")),
        user_id=str(state.get("user_id", "")),
        max_iterations=int(state.get("max_iterations", 0) or 0),
        research_plan=list(state.get("research_plan", [])),
        history_decision=str(state.get("history_decision", "")),
        review_decision=str(state.get("review_decision", "")),
        guardrails=state.get("guardrails"),
        run_metrics=state.get("run_metrics"),
        interrupt=interrupt,
        draft_report=state.get("draft_report"),
        search_results=list(state.get("search_results", [])),
        selected_evidence_ids=list(state.get("selected_evidence_ids", [])),
        selected_evidence=list(state.get("selected_evidence", [])),
        final_report=state.get("final_report"),
        reused_topic=state.get("reused_topic"),
    )


@api.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.post("/api/sessions", response_model=CreateSessionResponse)
def create_session() -> CreateSessionResponse:
    return CreateSessionResponse(thread_id=f"ui-{uuid4().hex}")


@api.get("/api/runs/{thread_id}", response_model=RunSnapshotResponse)
def get_run_snapshot(thread_id: str) -> RunSnapshotResponse:
    return _snapshot_for_thread(thread_id)


@api.post("/api/runs/start", response_model=RunSnapshotResponse)
def start_run(request: StartResearchRequest) -> RunSnapshotResponse:
    try:
        start_research_run(
            research_app,
            question=request.question,
            user_id=request.user_id,
            max_iterations=request.max_iterations,
            config=_config_for_thread(request.thread_id),
        )
    except Exception as exc:
        _raise_run_error(exc, "The research run")
    return _snapshot_for_thread(request.thread_id)


@api.post("/api/runs/resume", response_model=RunSnapshotResponse)
def resume_run(request: ResumeResearchRequest) -> RunSnapshotResponse:
    try:
        resume_research_run(
            research_app,
            config=_config_for_thread(request.thread_id),
            decision=request.decision,
            human_feedback=request.human_feedback,
            selected_evidence_ids=request.selected_evidence_ids,
        )
    except Exception as exc:
        _raise_run_error(exc, "The research run")
    return _snapshot_for_thread(request.thread_id)


@api.post("/api/translate", response_model=TranslateTextResponse)
def translate_text(request: TranslateTextRequest) -> TranslateTextResponse:
    try:
        translated_text = GoogleTranslator(source="auto", target=request.target_language).translate(request.text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Translation failed: {exc}") from exc

    if not translated_text:
        raise HTTPException(status_code=400, detail="Translation failed: empty response")

    return TranslateTextResponse(
        translated_text=translated_text,
        target_language=request.target_language,
    )


app = api
