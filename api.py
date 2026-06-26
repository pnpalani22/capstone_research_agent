from __future__ import annotations

from uuid import uuid4

from deep_translator import GoogleTranslator
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
    HistoryInterruptModel,
    ResumeResearchRequest,
    ReviewInterruptModel,
    RunSnapshotResponse,
    StartResearchRequest,
    TranslateTextRequest,
    TranslateTextResponse,
)


research_app = create_research_app()

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
    start_research_run(
        research_app,
        question=request.question,
        user_id=request.user_id,
        max_iterations=request.max_iterations,
        config=_config_for_thread(request.thread_id),
    )
    return _snapshot_for_thread(request.thread_id)


@api.post("/api/runs/resume", response_model=RunSnapshotResponse)
def resume_run(request: ResumeResearchRequest) -> RunSnapshotResponse:
    resume_research_run(
        research_app,
        config=_config_for_thread(request.thread_id),
        decision=request.decision,
        human_feedback=request.human_feedback,
    )
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