from __future__ import annotations

from typing import Any
from uuid import uuid4

from langgraph.types import Command

from error_utils import friendly_api_error_message, is_token_exhaustion_error
from graph import build_app


def create_research_app():
    """Create a compiled research graph instance."""

    return build_app()


def build_run_config(thread_id: str | None = None) -> dict[str, Any]:
    """Build the LangGraph config for a single research thread."""

    return {"configurable": {"thread_id": thread_id or f"research-{uuid4().hex}"}}


def build_initial_state(question: str, user_id: str, max_iterations: int) -> dict[str, Any]:
    """Create the initial state payload for a new research question."""

    return {
        "question": question,
        "user_id": user_id,
        "max_iterations": max_iterations,
        "messages": [],
    }


def start_research_run(app, question: str, user_id: str, max_iterations: int, config: dict[str, Any]):
    """Run a new research question until completion or an interrupt."""

    return app.invoke(build_initial_state(question, user_id, max_iterations), config=config)


def resume_research_run(
    app,
    config: dict[str, Any],
    decision: str,
    human_feedback: str = "",
    selected_evidence_ids: list[str] | None = None,
):
    """Resume an interrupted research run with the chosen decision."""

    resume_value: str | dict[str, Any]
    payload: dict[str, Any] = {"resume": decision}
    if human_feedback.strip():
        payload["human_feedback"] = human_feedback.strip()
    if selected_evidence_ids:
        payload["selected_evidence_ids"] = list(selected_evidence_ids)
    resume_value = payload if len(payload) > 1 else decision

    return app.invoke(Command(resume=resume_value), config=config)


def get_pending_interrupt(app, config: dict[str, Any]) -> dict[str, Any] | None:
    """Return the current interrupt payload, if the run is waiting for input."""

    state = app.get_state(config)
    for task in getattr(state, "tasks", ()):
        interrupts = getattr(task, "interrupts", ())
        if interrupts:
            return interrupts[0].value
    return None


def get_run_state(app, config: dict[str, Any]) -> dict[str, Any]:
    """Return the current merged state values for the active thread."""

    state = app.get_state(config)
    values = getattr(state, "values", None)
    return values if isinstance(values, dict) else {}


def get_final_report(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the final report from a graph result payload."""

    return result.get("final_report")


def main():
    app = create_research_app()
    config = build_run_config("alice-research-1")

    try:
        question = input("Research question: ").strip() or "What is the impact of transformer architecture on NLP?"
        user_id = input("User id [alice]: ").strip() or "alice"

        result = start_research_run(
            app,
            question=question,
            user_id=user_id,
            max_iterations=2,
            config=config,
        )

        interrupt_payload = get_pending_interrupt(app, config)
        if interrupt_payload:
            print("Run paused for review:")
            print(interrupt_payload)
            return

        print("Final report:")
        print(get_final_report(result) or result)
    except Exception as exc:
        print(friendly_api_error_message(exc, "The CLI research run"), flush=True)
        if is_token_exhaustion_error(exc):
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
