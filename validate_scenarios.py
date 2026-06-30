from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

from history_store import load_persisted_history, save_persisted_history


ROOT = Path(__file__).resolve().parent
SCENARIO_FILE = ROOT / "validation_queries.json"


def _post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"detail": body or exc.reason}
        return exc.code, payload


def _create_session(base_url: str) -> str:
    status, payload = _post_json(f"{base_url}/sessions", {})
    if status >= 400:
        raise RuntimeError(f"Failed to create session: {payload}")
    return str(payload["thread_id"])


def _start_run(base_url: str, thread_id: str, query: str, user_id: str, max_iterations: int = 3) -> tuple[int, dict[str, Any]]:
    return _post_json(
        f"{base_url}/runs/start",
        {
            "thread_id": thread_id,
            "question": query,
            "user_id": user_id,
            "max_iterations": max_iterations,
        },
    )


def _resume_run(
    base_url: str,
    thread_id: str,
    decision: str,
    human_feedback: str = "",
    selected_evidence_ids: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    return _post_json(
        f"{base_url}/runs/resume",
        {
            "thread_id": thread_id,
            "decision": decision,
            "human_feedback": human_feedback,
            "selected_evidence_ids": selected_evidence_ids or [],
        },
    )


def _contains_terms(text: str, terms: list[str]) -> bool:
    normalized = text.lower()
    return all(term.lower() in normalized for term in terms)


def _distinct_sources(search_results: list[dict[str, Any]]) -> int:
    identities = {
        (
            str(item.get("title", "")).strip().lower(),
            str(item.get("url", "")).strip().lower(),
            str(item.get("tool_name", "")).strip().lower(),
        )
        for item in search_results
    }
    return len(identities)


def _assert(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def _reset_seed_history_for_user(scenarios: list[dict[str, Any]], user_id: str) -> None:
    """Remove prior validation seed outputs so full validation runs stay repeatable."""

    seed_questions = {
        str(item.get("query", "")).strip()
        for item in scenarios
        if item.get("category") == "history_seed"
    }
    if not seed_questions:
        return

    history = load_persisted_history()
    filtered = [
        item
        for item in history
        if not (
            str(item.get("user_id", "")).strip() == user_id
            and str(item.get("question", "")).strip() in seed_questions
        )
    ]
    if len(filtered) != len(history):
        save_persisted_history(filtered)


def _resolve_interrupts(base_url: str, thread_id: str, payload: dict[str, Any], expected: dict[str, Any]) -> tuple[int, dict[str, Any], list[str]]:
    """Resume known interrupt paths so validation can inspect later workflow stages."""

    actions_taken: list[str] = []
    status = 200
    target_draft_interrupt = expected.get("draft_review_interrupt")
    next_step = expected.get("next_step")

    while True:
        interrupt = payload.get("interrupt") or {}
        action = interrupt.get("action")
        if not action:
            return status, payload, actions_taken

        decision = None
        feedback = ""
        if action == "review_history_match" and target_draft_interrupt == "review_before_publish":
            decision = "start_fresh_plan"
        elif action == "review_history_match" and next_step == "publish_then_store":
            decision = "proceed_with_context"
        elif action == "select_evidence_for_report":
            current_evidence = interrupt.get("current_evidence") or []
            selected_ids = [
                str(item.get("chunk_id", "")).strip()
                for item in current_evidence[:1]
                if str(item.get("chunk_id", "")).strip()
            ]
            status, payload = _resume_run(
                base_url,
                thread_id,
                "selected_evidence",
                selected_evidence_ids=selected_ids,
            )
            actions_taken.append("selected_evidence")
            if status >= 400:
                return status, payload, actions_taken
            continue
        elif action == "review_before_publish" and next_step == "publish_then_store":
            decision = "approved"

        if decision is None:
            return status, payload, actions_taken

        status, payload = _resume_run(base_url, thread_id, decision, human_feedback=feedback)
        actions_taken.append(decision)
        if status >= 400:
            return status, payload, actions_taken


def _evaluate_scenario(base_url: str, scenario: dict[str, Any], *, user_id: str) -> tuple[bool, list[str]]:
    scenario_id = str(scenario["id"])
    query = str(scenario["query"])
    expected = dict(scenario.get("expected", {}))
    failures: list[str] = []

    thread_id = _create_session(base_url)
    status, payload = _start_run(base_url, thread_id, query, user_id=user_id)

    if expected.get("result") == "request_error":
        detail = payload.get("detail")
        if isinstance(detail, list):
            detail = json.dumps(detail)
        _assert(status >= 400, f"{scenario_id}: expected request error, got {status}", failures)
        _assert(expected.get("message") in str(detail), f"{scenario_id}: expected message '{expected.get('message')}', got '{detail}'", failures)
        return not failures, failures

    _assert(status < 400, f"{scenario_id}: start_run failed with status {status}: {payload}", failures)
    if status >= 400:
        return False, failures

    status, payload, actions_taken = _resolve_interrupts(base_url, thread_id, payload, expected)
    _assert(status < 400, f"{scenario_id}: resume failed with status {status}: {payload}", failures)
    if status >= 400:
        return False, failures

    guardrails = payload.get("guardrails") or {}
    metrics = payload.get("run_metrics") or {}
    interrupt = payload.get("interrupt") or {}
    final_report = payload.get("final_report") or {}
    search_results = payload.get("search_results") or []

    if "guardrail_status" in expected:
        _assert(guardrails.get("status") == expected["guardrail_status"], f"{scenario_id}: guardrail status expected {expected['guardrail_status']}, got {guardrails.get('status')}", failures)
    if "recommended_action" in expected:
        _assert(guardrails.get("recommended_action") == expected["recommended_action"], f"{scenario_id}: recommended_action expected {expected['recommended_action']}, got {guardrails.get('recommended_action')}", failures)
    if "risk_flags" in expected:
        current_risks = set(guardrails.get("risk_flags") or [])
        wanted_risks = set(expected["risk_flags"])
        _assert(wanted_risks.issubset(current_risks), f"{scenario_id}: missing risk flags {sorted(wanted_risks - current_risks)} from {sorted(current_risks)}", failures)
    if "allowed_tools" in expected:
        _assert(list(guardrails.get("allowed_tools") or []) == list(expected["allowed_tools"]), f"{scenario_id}: allowed_tools expected {expected['allowed_tools']}, got {guardrails.get('allowed_tools')}", failures)
    if "allowed_tools_contains" in expected:
        current_tools = set(guardrails.get("allowed_tools") or [])
        required_tools = set(expected["allowed_tools_contains"])
        _assert(required_tools.issubset(current_tools), f"{scenario_id}: expected tools {sorted(required_tools)} to be included in {sorted(current_tools)}", failures)
    if "final_title" in expected:
        _assert(final_report.get("title") == expected["final_title"], f"{scenario_id}: final title expected {expected['final_title']}, got {final_report.get('title')}", failures)
    if "interrupt_action" in expected:
        _assert(interrupt.get("action") == expected["interrupt_action"], f"{scenario_id}: interrupt action expected {expected['interrupt_action']}, got {interrupt.get('action')}", failures)
    if "draft_review_interrupt" in expected:
        _assert(interrupt.get("action") == expected["draft_review_interrupt"], f"{scenario_id}: draft interrupt expected {expected['draft_review_interrupt']}, got {interrupt.get('action')}", failures)
    if "sanitized_question" in expected:
        _assert(guardrails.get("sanitized_question") == expected["sanitized_question"], f"{scenario_id}: sanitized question mismatch", failures)
    if "minimum_warning_contains" in expected:
        warnings = " ".join(guardrails.get("warnings") or []).lower()
        _assert(str(expected["minimum_warning_contains"]).lower() in warnings, f"{scenario_id}: warning did not contain {expected['minimum_warning_contains']}", failures)
    if "history_match_type" in expected:
        match_type = interrupt.get("match_type") if interrupt.get("action") == "review_history_match" else "new"
        _assert(match_type == expected["history_match_type"], f"{scenario_id}: history match expected {expected['history_match_type']}, got {match_type}", failures)
    if "history_interrupt_expected" in expected:
        has_history_interrupt = interrupt.get("action") == "review_history_match"
        _assert(has_history_interrupt == bool(expected["history_interrupt_expected"]), f"{scenario_id}: history interrupt expected {expected['history_interrupt_expected']}, got {has_history_interrupt}", failures)
    if "monitor_metrics" in expected:
        for metric_name in expected["monitor_metrics"]:
            _assert(metric_name in metrics, f"{scenario_id}: metric {metric_name} missing from run_metrics", failures)
    if "minimum_distinct_sources_in_top_results" in expected:
        distinct_sources = _distinct_sources(search_results[:8])
        _assert(distinct_sources >= int(expected["minimum_distinct_sources_in_top_results"]), f"{scenario_id}: distinct sources expected >= {expected['minimum_distinct_sources_in_top_results']}, got {distinct_sources}", failures)
    if "top_evidence_should_reference" in expected:
        combined_text = " ".join(
            f"{item.get('title', '')} {item.get('snippet', '')}"
            for item in search_results[:5]
        )
        _assert(_contains_terms(combined_text, list(expected["top_evidence_should_reference"])), f"{scenario_id}: top evidence missing expected terms {expected['top_evidence_should_reference']}", failures)
    if expected.get("require_final_report"):
        _assert(bool(final_report), f"{scenario_id}: expected final_report after approvals/resumes", failures)
    if "resume_actions_contains" in expected:
        action_set = set(actions_taken)
        required_actions = set(expected["resume_actions_contains"])
        _assert(required_actions.issubset(action_set), f"{scenario_id}: expected resume actions {sorted(required_actions)}, got {actions_taken}", failures)

    return not failures, failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run validation scenarios against the local Deep Research Agent API.")
    parser.add_argument("--base-url", default="http://localhost:8000/api", help="Base API URL")
    parser.add_argument("--category", action="append", default=[], help="Run only matching scenario categories")
    parser.add_argument("--user-id", default="validation-runner", help="User id for generated runs")
    args = parser.parse_args()

    scenario_payload = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))
    scenarios = list(scenario_payload.get("scenarios", []))
    if args.category:
        wanted = set(args.category)
        scenarios = [item for item in scenarios if item.get("category") in wanted]
    _reset_seed_history_for_user(scenarios, args.user_id)

    failures: list[str] = []
    passed = 0
    for scenario in scenarios:
        ok, scenario_failures = _evaluate_scenario(args.base_url, scenario, user_id=args.user_id)
        if ok:
            passed += 1
            print(f"PASS {scenario['id']}")
            continue
        print(f"FAIL {scenario['id']}")
        for item in scenario_failures:
            print(f"  - {item}")
        failures.extend(scenario_failures)

    print(f"\nSummary: {passed}/{len(scenarios)} scenarios passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
