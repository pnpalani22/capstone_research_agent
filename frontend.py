from __future__ import annotations

from html import escape
from uuid import uuid4

import streamlit as st

from error_utils import friendly_api_error_message, friendly_token_exhaustion_message, is_token_exhaustion_error
from app import (
    build_run_config,
    create_research_app,
    get_final_report,
    get_pending_interrupt,
    get_run_state,
    resume_research_run,
    start_research_run,
)


st.set_page_config(
    page_title="Deep Research Agent",
    page_icon="Research",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Source+Serif+4:wght@400;600&display=swap');

        :root {
            --bg: linear-gradient(180deg, #f5efe2 0%, #fffaf1 48%, #f3f7f4 100%);
            --panel: rgba(255, 252, 245, 0.88);
            --ink: #1f2a24;
            --muted: #56655d;
            --accent: #0f766e;
            --accent-soft: rgba(15, 118, 110, 0.12);
            --border: rgba(31, 42, 36, 0.12);
            --shadow: 0 18px 40px rgba(58, 70, 63, 0.10);
        }

        .stApp {
            background: var(--bg);
            color: var(--ink);
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif;
            color: var(--ink);
            letter-spacing: -0.03em;
        }

        p, li, label, div[data-testid="stMarkdownContainer"] {
            font-family: 'Source Serif 4', serif;
        }

        .hero-card,
        .panel-card,
        .match-card,
        .report-card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(12px);
        }

        .hero-card {
            padding: 1.5rem 1.6rem;
            margin-bottom: 1rem;
            position: relative;
            overflow: hidden;
        }

        .hero-card::after {
            content: "";
            position: absolute;
            inset: auto -5% -25% auto;
            width: 220px;
            height: 220px;
            background: radial-gradient(circle, rgba(15, 118, 110, 0.20), transparent 62%);
        }

        .hero-kicker {
            font-family: 'Space Grotesk', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-size: 0.8rem;
            color: var(--accent);
            margin-bottom: 0.6rem;
        }

        .hero-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2.6rem;
            line-height: 1.05;
            margin: 0;
            max-width: 11ch;
        }

        .hero-copy {
            color: var(--muted);
            font-size: 1.05rem;
            max-width: 58ch;
            margin-top: 0.75rem;
            margin-bottom: 0;
        }

        .panel-card,
        .report-card {
            padding: 1.1rem 1.2rem;
        }

        .match-card {
            padding: 1rem 1.1rem;
            margin-bottom: 0.9rem;
        }

        .meta-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.9rem 0 0.4rem;
        }

        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: var(--accent-soft);
            color: var(--accent);
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.85rem;
        }

        .section-label {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--accent);
            margin-bottom: 0.6rem;
        }

        .small-note {
            color: var(--muted);
            font-size: 0.95rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def _get_app():
    return create_research_app()


def _ensure_session() -> None:
    if "app" not in st.session_state:
        st.session_state.app = _get_app()
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = f"ui-{uuid4().hex}"
    if "config" not in st.session_state:
        st.session_state.config = build_run_config(st.session_state.thread_id)
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "submitted_question" not in st.session_state:
        st.session_state.submitted_question = ""
    if "fatal_error" not in st.session_state:
        st.session_state.fatal_error = ""


def _reset_session() -> None:
    st.session_state.thread_id = f"ui-{uuid4().hex}"
    st.session_state.config = build_run_config(st.session_state.thread_id)
    st.session_state.last_result = None
    st.session_state.submitted_question = ""
    st.session_state.fatal_error = ""


def _mark_fatal_error(exc: Exception, context: str) -> None:
    if is_token_exhaustion_error(exc):
        st.session_state.fatal_error = friendly_token_exhaustion_message(context)
    else:
        st.session_state.fatal_error = friendly_api_error_message(exc, context)


def _start_run(question: str, user_id: str, max_iterations: int) -> None:
    st.session_state.submitted_question = question
    try:
        start_research_run(
            st.session_state.app,
            question=question,
            user_id=user_id,
            max_iterations=max_iterations,
            config=st.session_state.config,
        )
        st.session_state.last_result = get_run_state(st.session_state.app, st.session_state.config)
    except Exception as exc:
        _mark_fatal_error(exc, "The research session")
        st.error(st.session_state.fatal_error)
        st.stop()


def _resume_run(decision: str, human_feedback: str = "") -> None:
    try:
        resume_research_run(
            st.session_state.app,
            config=st.session_state.config,
            decision=decision,
            human_feedback=human_feedback,
        )
        st.session_state.last_result = get_run_state(st.session_state.app, st.session_state.config)
    except Exception as exc:
        _mark_fatal_error(exc, "The research session")
        st.error(st.session_state.fatal_error)
        st.stop()


def _render_hero() -> None:
    st.markdown(
        """
        <section class="hero-card">
            <div class="hero-kicker">Capstone Research Workflow</div>
            <h1 class="hero-title">Ask, review, refine, publish.</h1>
            <p class="hero-copy">This interface keeps the existing LangGraph loop intact while giving the user a proper question workflow, history-match review, and draft approval step.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> tuple[str, int]:
    with st.sidebar:
        st.markdown("### Session controls")
        user_id = st.text_input("User id", value="analyst-1")
        max_iterations = st.slider("Search rounds", min_value=1, max_value=6, value=3)
        st.caption(f"Thread id: {st.session_state.thread_id}")
        if st.button("Start new session", use_container_width=True):
            _reset_session()
            st.rerun()
        st.markdown("### Suggested improvements")
        st.markdown(
            """
            1. Persist history in a real store instead of in-memory only.
            2. Add source scoring and deduplication before synthesis.
            3. Stream intermediate tool activity so long runs feel transparent.
            4. Add automated tests for interrupt and resume paths.
            """
        )
    return user_id, max_iterations


def _render_question_panel(user_id: str, max_iterations: int) -> None:
    st.markdown('<section class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Research question</div>', unsafe_allow_html=True)
    with st.form("question_form"):
        question = st.text_area(
            "What do you want to research?",
            value=st.session_state.submitted_question,
            height=140,
            placeholder="Example: How do retrieval-augmented generation systems improve factual accuracy in enterprise assistants?",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Run research", use_container_width=True)
    st.markdown('</section>', unsafe_allow_html=True)

    if submitted:
        if question.strip():
            with st.spinner("Running the research graph..."):
                _start_run(question.strip(), user_id=user_id, max_iterations=max_iterations)
            st.rerun()
        st.warning("Enter a question before starting the run.")


def _render_history_interrupt(payload: dict[str, object]) -> None:
    st.markdown('<section class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">History review</div>', unsafe_allow_html=True)
    st.write(payload.get("rationale", "A related history match was found."))
    st.markdown('<div class="meta-row">', unsafe_allow_html=True)
    st.markdown(
        f'<span class="meta-pill">Match type: {escape(str(payload.get("match_type", "unknown")))}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<span class="meta-pill">Question: {escape(str(payload.get("current_question", "")))}</span>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    for match in payload.get("matches", []):
        question = escape(str(match.get("question") or "Unknown question"))
        title = escape(str(match.get("title") or "Untitled report"))
        summary = escape(str(match.get("summary") or "No summary available."))
        published_report = escape(str(match.get("published_report") or ""))
        st.markdown(
            f"""
            <article class="match-card">
                <p><strong>Previous query:</strong> {question}</p>
                <h3>{title}</h3>
                <p><strong>Summary:</strong> {summary}</p>
                <p class="small-note"><strong>Published report:</strong> {published_report}</p>
            </article>
            """,
            unsafe_allow_html=True,
        )

    col1, col2, col3 = st.columns(3)
    if col1.button("Use as context", use_container_width=True):
        with st.spinner("Continuing with prior context..."):
            _resume_run("proceed_with_context")
        st.rerun()
    if col2.button("Start fresh", use_container_width=True):
        with st.spinner("Starting a fresh plan..."):
            _resume_run("start_fresh_plan")
        st.rerun()
    if col3.button("Reuse best match", use_container_width=True):
        with st.spinner("Reusing the stored report..."):
            _resume_run("reuse_existing")
        st.rerun()
    st.markdown('</section>', unsafe_allow_html=True)


def _render_review_interrupt(payload: dict[str, object]) -> None:
    draft = payload.get("draft", {})
    findings = draft.get("findings", []) if isinstance(draft, dict) else []
    sources = draft.get("sources", []) if isinstance(draft, dict) else []

    st.markdown('<section class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Draft review</div>', unsafe_allow_html=True)
    st.subheader(str(draft.get("title", "Draft report")))
    st.write(draft.get("summary", "No summary available."))
    if findings:
        st.markdown("**Key findings**")
        for item in findings:
            st.write(f"- {item}")
    if sources:
        st.markdown("**Sources**")
        for source in sources:
            if isinstance(source, dict):
                st.write(f"- {source.get('title', 'Untitled source')} - {source.get('url', '')}")
            else:
                st.write(f"- {source}")

    with st.form("review_form"):
        feedback = st.text_area(
            "Reviewer note",
            height=110,
            placeholder="Optional guidance for the final report.",
        )
        approve = st.form_submit_button("Approve and publish", use_container_width=True)
        edit_publish = st.form_submit_button("Apply note and publish", use_container_width=True)
        reject = st.form_submit_button("Reject and re-plan", use_container_width=True)

    if approve:
        with st.spinner("Publishing the approved draft..."):
            _resume_run("approved")
        st.rerun()
    if edit_publish:
        with st.spinner("Applying feedback and publishing..."):
            _resume_run("edited", human_feedback=feedback)
        st.rerun()
    if reject:
        with st.spinner("Sending the draft back for another planning round..."):
            _resume_run("rejected", human_feedback=feedback)
        st.rerun()
    st.markdown('</section>', unsafe_allow_html=True)


def _render_final_report(result: dict[str, object] | None) -> None:
    if not result:
        return

    final_report = get_final_report(result)
    if not final_report:
        return

    st.markdown('<section class="report-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Published report</div>', unsafe_allow_html=True)

    reused_topic = result.get("reused_topic") if isinstance(result, dict) else None
    if isinstance(reused_topic, dict):
        reused_question = reused_topic.get("question", "Unknown question")
        reused_report = reused_topic.get("report", {})
        reused_answer = reused_report.get("published_report", "No published answer available.") if isinstance(reused_report, dict) else "No published answer available."
        st.success("Reused from history. No new LLM research run was executed after you selected reuse.")
        st.info(
            "This result was reused from history.\n\n"
            f"Previous query: {reused_question}\n\n"
            f"Previous answer: {reused_answer}"
        )
    else:
        st.success("Fresh research run executed. The planner, search, reasoning, and synthesis steps used the LLM for this answer.")

    st.header(str(final_report.get("title", "Research report")))
    st.write(final_report.get("summary", "No summary available."))

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("**Published answer**")
        st.write(final_report.get("published_report", "No published report available."))
        findings = final_report.get("key_findings", [])
        if findings:
            st.markdown("**Findings**")
            for item in findings:
                st.write(f"- {item}")
    with col2:
        confidence = final_report.get("confidence", 0.0)
        st.metric("Confidence", f"{float(confidence):.0%}")
        sources = final_report.get("sources", [])
        if sources:
            st.markdown("**Sources**")
            for source in sources:
                if isinstance(source, dict):
                    title = source.get("title", "Untitled source")
                    url = source.get("url", "")
                else:
                    title = str(source)
                    url = ""
                if url:
                    st.markdown(f"- [{title}]({url})")
                else:
                    st.write(f"- {title}")
    st.markdown('</section>', unsafe_allow_html=True)


def main() -> None:
    _inject_styles()
    _ensure_session()

    if st.session_state.fatal_error:
        st.error(st.session_state.fatal_error)
        st.stop()

    _render_hero()
    user_id, max_iterations = _render_sidebar()

    left_col, right_col = st.columns([1.6, 1], gap="large")
    with left_col:
        _render_question_panel(user_id=user_id, max_iterations=max_iterations)
        interrupt_payload = get_pending_interrupt(st.session_state.app, st.session_state.config)
        if interrupt_payload:
            action = interrupt_payload.get("action")
            if action == "review_history_match":
                _render_history_interrupt(interrupt_payload)
            elif action == "review_before_publish":
                _render_review_interrupt(interrupt_payload)
        else:
            _render_final_report(st.session_state.last_result)

    with right_col:
        st.markdown('<section class="panel-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Run snapshot</div>', unsafe_allow_html=True)
        if st.session_state.submitted_question:
            st.write(st.session_state.submitted_question)
        else:
            st.write("No question submitted yet.")
        st.caption("The graph pauses here whenever it needs a history decision or report approval.")
        st.markdown('</section>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
