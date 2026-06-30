from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.store.memory import InMemoryStore

from nodes import (
    apply_edit_node,
    capture_tool_results_node,
    evaluate_guardrails_node,
    guardrail_block_node,
    history_review_gate_node,
    history_review_node,
    initialize_run_node,
    load_history_node,
    planner_node,
    prepare_search_node,
    publish_node,
    reason_node,
    route_after_guardrail_evaluation,
    review_gate_node,
    reuse_existing_report_node,
    route_after_history_review_gate,
    route_after_reason,
    save_history_node,
    synthesise_node,
    evidence_selection_gate_node,
)

from state import ResearchState
from tools import build_tools


def _canonical_tool_name(tool_name: str) -> str:
    """Map concrete LangChain tool names to the guardrail-facing tool keys."""

    normalized = str(tool_name or "").strip().lower()
    if "wiki" in normalized:
        return "wikipedia"
    if "tavily" in normalized:
        return "tavily"
    if "weather" in normalized:
        return "weather"
    return normalized


def _allowed_tools_for_state(state: ResearchState, tools: list):
    """Filter concrete tools to the currently allowed guardrail set."""

    allowed = {
        str(item).strip().lower()
        for item in state.get("guardrails", {}).get("allowed_tools", ["tavily", "wikipedia", "weather"])
    }
    filtered = [tool for tool in tools if _canonical_tool_name(getattr(tool, "name", "")) in allowed]
    return filtered


def _tool_access_gate_node(state: ResearchState, tools: list) -> dict[str, object]:
    """Block the workflow when no concrete tools are available for the current guardrail state."""

    if _allowed_tools_for_state(state, tools):
        return {}

    guardrails = dict(state.get("guardrails", {}))
    guardrails.update(
        {
            "status": "blocked",
            "recommended_action": "block",
            "explanation": "No allowed research tools are available for this request, so the workflow stopped safely.",
            "clarifying_question": "Revise the request or guardrail policy so at least one approved research tool is available.",
        }
    )
    return {"guardrails": guardrails}


def _build_search_messages(state: ResearchState):
    """Build a clean tool-calling prompt without replaying old tool-call history."""

    research_plan = state.get("research_plan", [])
    search_results = state.get("search_results", [])[-4:]
    retrieval_context = state.get("retrieval_context", [])[:2]

    return [
        SystemMessage(
            content=(
                "You are a research search assistant. Use at most one tool call. "
                "Prefer high-signal searches, diversify sources, and avoid repeating a query unless it clearly closes an evidence gap."
            )
        ),
        HumanMessage(
            content=(
                f"Research question: {state['question']}\n\n"
                f"Allowed tools: {state.get('guardrails', {}).get('allowed_tools', ['tavily', 'wikipedia', 'weather'])}\n\n"
                f"Iteration: {state.get('iteration', 0)}\n\n"
                f"Research plan: {research_plan[:3]}\n\n"
                f"Retrieved history context: {retrieval_context}\n\n"
                f"Prior search results: {search_results}\n\n"
                "Choose the next best search action. Only call a tool from the allowed tools list."
            )
        ),
    ]

def build_app():
    """Build and compile the Deep Research Agent graph."""

    load_dotenv()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    tools = build_tools()

    builder = StateGraph(ResearchState)

    builder.add_node("initialize_run_node", initialize_run_node)
    builder.add_node(
        "evaluate_guardrails_node",
        lambda state: evaluate_guardrails_node(state, llm=llm),
    )
    builder.add_node("guardrail_block_node", guardrail_block_node)

    builder.add_node(
        "load_history_node",
        lambda state, store: load_history_node(state, store=store),
    )

    builder.add_node(
        "history_review_node",
        lambda state: history_review_node(state, llm=llm, embeddings=embeddings),
    )

    builder.add_node("history_review_gate_node", history_review_gate_node)

    builder.add_node("reuse_existing_report_node", reuse_existing_report_node)
    
    builder.add_node(
        "planner_node",
        lambda state: planner_node(state, llm=llm),
    )
    
    builder.add_node("prepare_search_node", prepare_search_node)
    builder.add_node(
        "tool_access_gate_node",
        lambda state: _tool_access_gate_node(state, tools),
    )
    
    builder.add_node(
        "search_node",
        lambda state: {
            "messages": [
                llm.bind_tools(_allowed_tools_for_state(state, tools)).invoke(_build_search_messages(state))
            ]
        },
    )
    
    builder.add_node(
        "tools",
        lambda state: ToolNode(
            _allowed_tools_for_state(state, tools),
            handle_tool_errors="Tool call failed. Continue with available results.",
        ).invoke(state),
    )
    builder.add_node("capture_tool_results_node", capture_tool_results_node)
    
    builder.add_node(
        "reason_node",
        lambda state: reason_node(state, llm=llm),
    )
    builder.add_node("evidence_selection_gate_node", evidence_selection_gate_node)
    
    builder.add_node(
        "synthesise_node",
        lambda state: synthesise_node(state, llm=llm),
    )
    
    builder.add_node("review_gate_node", review_gate_node)
    
    builder.add_node("apply_edit_node", apply_edit_node)
    
    builder.add_node(
        "publish_node",
        lambda state: publish_node(state, llm=llm),
    )
    
    builder.add_node(
        "save_history_node",
        lambda state, store: save_history_node(state, store=store),
    )

    builder.add_edge(START, "initialize_run_node")
    builder.add_edge("initialize_run_node", "evaluate_guardrails_node")
    builder.add_conditional_edges(
        "evaluate_guardrails_node",
        route_after_guardrail_evaluation,
        {
            "continue": "load_history_node",
            "blocked": "guardrail_block_node",
        },
    )
    builder.add_edge("load_history_node", "history_review_node")
    builder.add_edge("history_review_node", "history_review_gate_node")
    builder.add_conditional_edges(
        "history_review_gate_node",
        route_after_history_review_gate,
        {
            "proceed_with_context": "planner_node",
            "start_fresh_plan": "planner_node",
            "reuse_existing": "reuse_existing_report_node",
        },
    )
    builder.add_edge("planner_node", "prepare_search_node")
    builder.add_edge("prepare_search_node", "tool_access_gate_node")
    builder.add_conditional_edges(
        "tool_access_gate_node",
        route_after_guardrail_evaluation,
        {
            "continue": "search_node",
            "blocked": "guardrail_block_node",
        },
    )

    builder.add_conditional_edges(
        "search_node",
        tools_condition,
        {
            "tools": "tools",
            END: "reason_node",
        },
    )
    builder.add_edge("tools", "capture_tool_results_node")
    builder.add_edge("capture_tool_results_node", "reason_node")

    builder.add_conditional_edges(
        "reason_node",
        route_after_reason,
        {
            "prepare_search_node": "prepare_search_node",
            "evidence_selection_gate_node": "evidence_selection_gate_node",
            "synthesise_node": "synthesise_node",
        },
    )

    builder.add_edge("evidence_selection_gate_node", "synthesise_node")
    builder.add_edge("synthesise_node", "review_gate_node")
    builder.add_conditional_edges(
        "review_gate_node",
        lambda state: state.get("review_decision", ""),
        {
            "approved": "publish_node",
            "edited": "apply_edit_node",
            "rejected": "planner_node",
        },
    )
    builder.add_edge("apply_edit_node", "publish_node")
    builder.add_edge("publish_node", "save_history_node")
    builder.add_edge("reuse_existing_report_node", "save_history_node")
    builder.add_edge("save_history_node", END)
    builder.add_edge("guardrail_block_node", END)

    return builder.compile(
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
