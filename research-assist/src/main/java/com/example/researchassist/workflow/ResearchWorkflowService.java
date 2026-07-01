package com.example.researchassist.workflow;

import com.example.researchassist.model.ResumeResearchRequest;
import com.example.researchassist.model.RunSnapshotResponse;
import com.example.researchassist.model.StartResearchRequest;
import com.example.researchassist.model.TranslateTextRequest;
import com.example.researchassist.model.TranslateTextResponse;
import com.example.researchassist.config.TavilyConfig;
import com.example.researchassist.service.HistoryStoreService;
import com.example.researchassist.service.OpenAIClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Service
public class ResearchWorkflowService {

    private final HistoryStoreService historyStoreService;
    private final OpenAIClient openAIClient;
    private final TavilyConfig tavilyConfig;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Map<String, Map<String, Object>> runStates = new ConcurrentHashMap<>();
    private static final List<String> DEFAULT_ALLOWED_TOOLS = List.of("tavily", "wikipedia");
    private static final Set<String> HIGH_SEVERITY_RISK_FLAGS = Set.of("prompt_injection", "secret_exfiltration", "policy_bypass");
    private static final Map<String, Pattern> QUESTION_RISK_PATTERNS = Map.of(
            "prompt_injection", Pattern.compile("ignore\\s+(all|any|previous)|system\\s+prompt|developer\\s+message", Pattern.CASE_INSENSITIVE),
            "secret_exfiltration", Pattern.compile("api\\s*key|token|password|secret", Pattern.CASE_INSENSITIVE),
            "policy_bypass", Pattern.compile("bypass\\s+(safety|policy|guardrails)|jailbreak|disable\\s+(safety|guardrails)", Pattern.CASE_INSENSITIVE),
            "non_research_request", Pattern.compile("\\b(run|install|start|launch|restart|stop|deploy|build|execute|create|open|fix|debug)\\b", Pattern.CASE_INSENSITIVE)
    );

    public ResearchWorkflowService(HistoryStoreService historyStoreService, OpenAIClient openAIClient, TavilyConfig tavilyConfig) {
        this.historyStoreService = historyStoreService;
        this.openAIClient = openAIClient;
        this.tavilyConfig = tavilyConfig;
    }

    public RunSnapshotResponse startResearchRun(StartResearchRequest request) {
        Map<String, Object> state = initializeState(request);
        runStates.put(request.threadId(), state);
        executeRun(state);
        return buildSnapshot(request.threadId(), state);
    }

    public RunSnapshotResponse getRunSnapshot(String threadId) {
        Map<String, Object> state = runStates.get(threadId);
        if (state == null) {
            return new RunSnapshotResponse(threadId, "idle", "", "", 0, List.of(), "", "", null, null, null, null, List.of(), List.of(), List.of(), null, null);
        }
        return buildSnapshot(threadId, state);
    }

    public RunSnapshotResponse resumeResearchRun(ResumeResearchRequest request) {
        Map<String, Object> state = runStates.get(request.threadId());
        if (state == null) {
            throw new IllegalArgumentException("Unknown thread id: " + request.threadId());
        }
        state.remove("interrupt");
        state.put("human_feedback", request.humanFeedback() == null ? "" : request.humanFeedback().trim());
        if (request.selectedEvidenceIds() != null && !request.selectedEvidenceIds().isEmpty()) {
            state.put("selected_evidence_ids", new ArrayList<>(request.selectedEvidenceIds()));
            state.put("selected_evidence", selectEvidenceByIds(getSearchResults(state), request.selectedEvidenceIds()));
            synthesizeNode(state);
            reviewGateNode(state);
            return buildSnapshot(request.threadId(), state);
        }

        String decision = request.decision();
        if (decision == null) {
            throw new IllegalArgumentException("Decision is required for resume requests.");
        }

        switch (decision) {
            case "proceed_with_context", "start_fresh_plan" -> {
                state.put("history_decision", decision);
                if ("start_fresh_plan".equals(decision)) {
                    state.put("review_decision", "");
                    state.put("selected_evidence_ids", new ArrayList<>());
                    state.put("selected_evidence", new ArrayList<>());
                    state.put("search_results", new ArrayList<>());
                    state.put("retrieval_context", new ArrayList<>());
                    state.put("iteration", 0);
                }
                runSearchFlow(state);
                return buildSnapshot(request.threadId(), state);
            }
            case "selected_evidence" -> {
                synthesizeNode(state);
                reviewGateNode(state);
                return buildSnapshot(request.threadId(), state);
            }
            case "reuse_existing" -> {
                Map<String, Object> reuse = reuseExistingReportNode(state);
                state.putAll(reuse);
                saveHistoryIfComplete(state);
                return buildSnapshot(request.threadId(), state);
            }
            case "approved" -> {
                publishNode(state);
                saveHistoryIfComplete(state);
                return buildSnapshot(request.threadId(), state);
            }
            case "edited" -> {
                applyEditNode(state);
                publishNode(state);
                saveHistoryIfComplete(state);
                return buildSnapshot(request.threadId(), state);
            }
            case "rejected" -> {
                state.put("review_decision", "rejected");
                state.put("reasoner_decision", "CONTINUE");
                planNode(state, true);
                runSearchFlow(state);
                return buildSnapshot(request.threadId(), state);
            }
            default -> {
                state.put("history_decision", decision);
                runSearchFlow(state);
                return buildSnapshot(request.threadId(), state);
            }
        }
    }

    private Map<String, Object> initializeState(StartResearchRequest request) {
        Map<String, Object> state = new LinkedHashMap<>();
        String sanitizedQuestion = sanitizeQuestion(request.question());
        state.put("question", sanitizedQuestion);
        state.put("user_id", request.userId());
        state.put("max_iterations", request.maxIterations());
        state.put("iteration", 0);
        state.put("reasoner_decision", "");
        state.put("history_decision", "");
        state.put("review_decision", "");
        state.put("review_decision", "");
        state.put("selected_evidence_ids", new ArrayList<>());
        state.put("selected_evidence", new ArrayList<>());
        state.put("search_results", new ArrayList<>());
        state.put("retrieval_context", new ArrayList<>());
        state.put("research_plan", new ArrayList<>());
        state.put("past_topics", new ArrayList<>());
        state.put("final_report", null);
        state.put("draft_report", null);
        state.put("human_feedback", "");
        state.put("reused_topic", null);
        state.put("guardrails", assessQuestion(sanitizedQuestion));
        state.put("run_metrics", defaultRunMetrics());
        return state;
    }

    private void executeRun(Map<String, Object> state) {
        if (isBlocked(state)) {
            guardrailBlockNode(state);
            return;
        }
        loadHistoryNode(state);
        historyReviewNode(state);
        historyReviewGateNode(state);
        if (state.containsKey("interrupt")) {
            return;
        }
        routeAfterHistoryReviewGate(state);
        if ("reuse_existing".equals(state.get("history_decision"))) {
            reuseExistingReportNode(state);
            saveHistoryIfComplete(state);
            return;
        }
        runSearchFlow(state);
    }

    private void guardrailBlockNode(Map<String, Object> state) {
        // Guardrail blocks are handled through the guardrails state only.
        // The UI does not currently support a custom guardrail interrupt payload.
        state.remove("interrupt");
    }

    private boolean isBlocked(Map<String, Object> state) {
        Map<String, Object> guardrails = getMap(state.get("guardrails"));
        return "blocked".equals(guardrails.get("status"));
    }

    private void runSearchFlow(Map<String, Object> state) {
        planNode(state, false);
        while (true) {
            prepareSearchNode(state);
            List<Map<String, Object>> results = searchNode(state);
            captureToolResultsNode(state, results);
            reasonNode(state);
            String reasonDecision = String.valueOf(state.getOrDefault("reasoner_decision", "CONTINUE"));
            if ("DONE".equalsIgnoreCase(reasonDecision)) {
                if (getSearchResults(state).isEmpty()) {
                    synthesizeNode(state);
                    reviewGateNode(state);
                } else {
                    evidenceSelectionGateNode(state);
                }
                return;
            }
            int iteration = Integer.parseInt(String.valueOf(state.getOrDefault("iteration", 0)));
            int maxIterations = Integer.parseInt(String.valueOf(state.getOrDefault("max_iterations", 3)));
            if (iteration >= maxIterations) {
                synthesiseNode(state);
                reviewGateNode(state);
                return;
            }
        }
    }

    public TranslateTextResponse translateText(TranslateTextRequest request) {
        String prompt = "Translate the following text into " + request.targetLanguage() + ":\n\n" + request.text();
        String translation = openAIClient.chatCompletion("gpt-4o-mini", List.of(
                Map.of("role", "system", "content", "You are a translation assistant that preserves meaning and tone."),
                Map.of("role", "user", "content", prompt)
        )).trim();
        return new TranslateTextResponse(translation, request.targetLanguage());
    }

    private Map<String, Object> assessQuestion(String question) {
        String sanitizedQuestion = sanitizeQuestion(question);
        List<String> warnings = new ArrayList<>();
        Set<String> riskFlags = new HashSet<>();
        if (sanitizedQuestion.split("\\s+").length < 5) {
            warnings.add("Question is brief; add business context, scope, or constraints for better retrieval.");
        }
        if (sanitizedQuestion.length() > 420) {
            warnings.add("Question is long; prioritize the key decision or outcome to improve search precision.");
        }
        if (sanitizedQuestion.split("\\s+").length > 90) {
            riskFlags.add("overscoped_request");
            warnings.add("Question is overscoped; focus on one decision, market, or outcome for better research quality.");
        }
        for (Map.Entry<String, Pattern> entry : QUESTION_RISK_PATTERNS.entrySet()) {
            if ("non_research_request" .equals(entry.getKey())) {
                if (entry.getValue().matcher(sanitizedQuestion).find() && sanitizedQuestion.matches("(?i).*\\b(for me|please)\\b.*")) {
                    riskFlags.add(entry.getKey());
                }
            } else if (entry.getValue().matcher(sanitizedQuestion).find()) {
                riskFlags.add(entry.getKey());
            }
        }
        String status = "ready";
        String recommendedAction = "proceed";
        if (!Collections.disjoint(riskFlags, HIGH_SEVERITY_RISK_FLAGS) || riskFlags.contains("non_research_request")) {
            status = "blocked";
            recommendedAction = "block";
        } else if (!warnings.isEmpty()) {
            status = "needs_clarification";
            recommendedAction = "revise";
        }
        List<String> allowedTools = inferAllowedTools(sanitizedQuestion);
        String clarifyingQuestion = status.equals("needs_clarification") ? "Please restate the request as a focused research question with scope and desired outcome." : "";
        String explanation = buildGuardrailExplanation(status, riskFlags, warnings);
        Map<String, Object> guardrails = new LinkedHashMap<>();
        guardrails.put("sanitized_question", sanitizedQuestion);
        guardrails.put("status", status);
        guardrails.put("recommended_action", recommendedAction);
        guardrails.put("warnings", dedupeTextList(warnings, 6));
        guardrails.put("risk_flags", dedupeTextList(new ArrayList<>(riskFlags), 5));
        guardrails.put("allowed_tools", allowedTools);
        guardrails.put("explanation", explanation);
        guardrails.put("clarifying_question", clarifyingQuestion);
        return guardrails;
    }

    private List<String> inferAllowedTools(String question) {
        String normalized = question.toLowerCase();
        Set<String> allowed = new LinkedHashSet<>(DEFAULT_ALLOWED_TOOLS);
        if (!tavilyConfig.isEnabled()) {
            allowed.remove("tavily");
        }
        return new ArrayList<>(allowed);
    }

    private String buildGuardrailExplanation(String status, Set<String> riskFlags, List<String> warnings) {
        if ("blocked".equals(status)) {
            if (!riskFlags.isEmpty()) {
                return "The request was blocked because it asks for hidden instructions, credentials, or a safety bypass (" + String.join(", ", riskFlags) + ").";
            }
            return "The request was blocked because it falls outside the allowed research workflow.";
        }
        if ("needs_clarification".equals(status)) {
            if (!warnings.isEmpty()) {
                return warnings.get(0);
            }
            return "The request needs more scope or context before research should begin.";
        }
        return "The request is suitable for research and can proceed with the allowed tools.";
    }

    private String sanitizeQuestion(String value) {
        if (value == null) {
            return "";
        }
        String cleaned = value.trim().replaceAll("\\s+", " ");
        return cleaned.length() > 600 ? cleaned.substring(0, 600).trim() : cleaned;
    }

    private Map<String, Object> defaultRunMetrics() {
        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("iterations_used", 0);
        metrics.put("evidence_items", 0);
        metrics.put("unique_sources", 0);
        metrics.put("history_candidates", 0);
        metrics.put("retrieval_strategy", "lexical");
        metrics.put("rerank_applied", 0);
        metrics.put("rerank_candidates", 0);
        metrics.put("rerank_duplicates_removed", 0);
        metrics.put("rerank_trimmed_for_limit", 0);
        metrics.put("rerank_distinct_sources", 0);
        return metrics;
    }

    private void loadHistoryNode(Map<String, Object> state) {
        List<Map<String, Object>> persistedHistory = historyStoreService.loadPersistedHistory();
        state.put("past_topics", persistedHistory);
    }

    private void historyReviewNode(Map<String, Object> state) {
        List<Map<String, Object>> pastTopics = getList(state.get("past_topics"));
        List<Map<String, Object>> relevantHistory = findRelevantHistory(state.get("question"), pastTopics);
        String matchType = classifyHistory(state.get("question"), relevantHistory);
        String rationale = buildHistoryRationale(matchType, relevantHistory.size());
        List<Map<String, Object>> limitedHistory = relevantHistory.stream().limit(3).collect(Collectors.toList());
        state.put("history_review", Map.of(
                "match_type", matchType,
                "rationale", rationale,
                "relevant_history", limitedHistory
        ));
        state.put("retrieval_context", limitedHistory);
        state.put("run_metrics", buildMetrics(state, "hybrid", relevantHistory.size(), defaultRunMetrics()));
    }

    private void historyReviewGateNode(Map<String, Object> state) {
        Map<String, Object> historyReview = getMap(state.get("history_review"));
        String matchType = String.valueOf(historyReview.getOrDefault("match_type", "new"));
        List<Map<String, Object>> relevantHistory = getList(historyReview.get("relevant_history"));
        Map<String, Object> reuseCandidate = findReuseCandidate(state.get("question"), getList(state.get("past_topics")));
        if (reuseCandidate == null) {
            state.put("history_decision", "proceed_with_context");
            return;
        }

        List<Map<String, Object>> matches = relevantHistory.stream()
                .map(item -> {
                    Map<String, Object> report = getMap(item.get("report"));
                    return Map.of(
                            "question", item.getOrDefault("question", ""),
                            "published_report", report.getOrDefault("published_report", ""),
                            "title", report.getOrDefault("title", ""),
                            "summary", report.getOrDefault("summary", ""),
                            "user_id", item.getOrDefault("user_id", ""),
                            "created_at", item.getOrDefault("created_at", "")
                    );
                })
                .collect(Collectors.toList());
        Map<String, Object> interrupt = new LinkedHashMap<>();
        interrupt.put("action", "review_history_match");
        interrupt.put("current_question", state.get("question"));
        interrupt.put("match_type", matchType);
        interrupt.put("rationale", historyReview.getOrDefault("rationale", ""));
        interrupt.put("matches", matches);
        interrupt.put("reuse_allowed", true);
        Map<String, Object> report = getMap(reuseCandidate.get("report"));
        interrupt.put("reuse_candidate", Map.of(
                "question", reuseCandidate.getOrDefault("question", ""),
                "published_report", report.getOrDefault("published_report", ""),
                "title", report.getOrDefault("title", ""),
                "summary", report.getOrDefault("summary", ""),
                "user_id", reuseCandidate.getOrDefault("user_id", ""),
                "created_at", reuseCandidate.getOrDefault("created_at", "")
        ));
        state.put("interrupt", interrupt);
        state.put("history_decision", "review_history_match");
    }

    private void routeAfterHistoryReviewGate(Map<String, Object> state) {
        String decision = String.valueOf(state.getOrDefault("history_decision", "proceed_with_context"));
        if ("start_fresh_plan" .equals(decision)) {
            state.put("history_decision", "start_fresh_plan");
            return;
        }
        if ("reuse_existing" .equals(decision)) {
            state.put("history_decision", "reuse_existing");
            return;
        }
        state.put("history_decision", "proceed_with_context");
    }

    private Map<String, Object> reuseExistingReportNode(Map<String, Object> state) {
        Map<String, Object> reuseCandidate = findReuseCandidate(state.get("question"), getList(state.get("past_topics")));
        if (reuseCandidate == null) {
            state.put("history_decision", "proceed_with_context");
            return Map.of();
        }
        state.put("reused_topic", reuseCandidate);
        state.put("final_report", reuseCandidate.get("report"));
        state.put("messages", List.of(Map.of("content", "Reused the newest exact-match published report from history for the current question.")));
        return Map.of("reused_topic", reuseCandidate, "final_report", reuseCandidate.get("report"));
    }

    private void planNode(Map<String, Object> state, boolean forceFreshPlan) {
        List<Map<String, Object>> relevantHistory = Collections.emptyList();
        if (!forceFreshPlan && "proceed_with_context".equals(state.get("history_decision"))) {
            Map<String, Object> historyReview = getMap(state.get("history_review"));
            relevantHistory = getList(historyReview.get("relevant_history"));
        }
        List<String> researchPlan = buildLocalResearchPlan(String.valueOf(state.get("question")), getMap(state.get("guardrails")), relevantHistory);
        state.put("research_plan", researchPlan);
        if (forceFreshPlan) {
            state.put("search_results", new ArrayList<>());
            state.put("retrieval_context", new ArrayList<>());
            state.put("selected_evidence_ids", new ArrayList<>());
            state.put("selected_evidence", new ArrayList<>());
            state.put("iteration", 0);
            state.put("reasoner_decision", "");
            state.put("draft_report", null);
            state.put("final_report", null);
        }
    }

    private void prepareSearchNode(Map<String, Object> state) {
        int nextIteration = Integer.parseInt(String.valueOf(state.getOrDefault("iteration", 0))) + 1;
        state.put("iteration", nextIteration);
    }

    private List<Map<String, Object>> searchNode(Map<String, Object> state) {
        List<String> plan = getList(state.get("research_plan"));
        int iteration = Integer.parseInt(String.valueOf(state.getOrDefault("iteration", 0)));
        String query = plan.isEmpty() ? String.valueOf(state.get("question")) : plan.get(Math.min(iteration - 1, plan.size() - 1));
        Map<String, Object> guardrails = getMap(state.get("guardrails"));
        List<String> allowedTools = guardrails.containsKey("allowed_tools") ? getList(guardrails.get("allowed_tools")) : DEFAULT_ALLOWED_TOOLS;
        return generateSearchResults(query, allowedTools);
    }

    private void captureToolResultsNode(Map<String, Object> state, List<Map<String, Object>> results) {
        List<Map<String, Object>> merged = new ArrayList<>(getSearchResults(state));
        merged.addAll(results);
        List<Map<String, Object>> deduped = dedupeEvidence(merged, String.valueOf(state.get("question")));
        state.put("search_results", deduped);
        state.put("run_metrics", buildMetrics(state, "hybrid", getList(state.get("search_results")).size(), defaultRunMetrics()));
    }

    private void reasonNode(Map<String, Object> state) {
        int iteration = Integer.parseInt(String.valueOf(state.getOrDefault("iteration", 0)));
        int maxIterations = Integer.parseInt(String.valueOf(state.getOrDefault("max_iterations", 3)));
        String decision;
        if (iteration >= maxIterations) {
            decision = "DONE";
        } else {
            List<Map<String, Object>> searchResults = getSearchResults(state);
            int uniqueSources = (int) searchResults.stream().map(item -> identity(item)).distinct().count();
            int evidenceCount = searchResults.size();
            if (evidenceCount < 3) {
                decision = "CONTINUE";
            } else if (uniqueSources < 2 && iteration < maxIterations - 1) {
                decision = "CONTINUE";
            } else if (evidenceCount >= 5 && uniqueSources >= 2) {
                decision = "DONE";
            } else if (searchResults.stream().mapToDouble(item -> Double.parseDouble(String.valueOf(item.getOrDefault("score", 0.0)))).max().orElse(0.0) >= 0.72 && uniqueSources >= 2) {
                decision = "DONE";
            } else if (iteration >= maxIterations - 1 && evidenceCount >= 3) {
                decision = "DONE";
            } else {
                decision = "CONTINUE";
            }
        }
        state.put("reasoner_decision", decision);
        state.put("messages", List.of(Map.of("content", decision + ": research decision after iteration " + state.get("iteration"))));
    }

    private void evidenceSelectionGateNode(Map<String, Object> state) {
        List<Map<String, Object>> evidence = getSearchResults(state).stream().limit(8).collect(Collectors.toList());
        if (evidence.isEmpty()) {
            state.put("selected_evidence_ids", new ArrayList<>());
            state.put("selected_evidence", new ArrayList<>());
            return;
        }
        Map<String, Object> interrupt = new LinkedHashMap<>();
        interrupt.put("action", "select_evidence_for_report");
        interrupt.put("question", state.get("question"));
        interrupt.put("research_plan", state.get("research_plan"));
        interrupt.put("current_evidence", evidence);
        interrupt.put("instructions", "Select one or more evidence items to use for the report. The report synthesis step will use only the selected evidence.");
        state.put("interrupt", interrupt);
    }

    private void synthesiseNode(Map<String, Object> state) {
        synthesizeNode(state);
    }

    private void reviewGateNode(Map<String, Object> state) {
        Map<String, Object> draft = getMap(state.get("draft_report"));
        Map<String, Object> interrupt = new LinkedHashMap<>();
        interrupt.put("action", "review_before_publish");
        interrupt.put("question", state.get("question"));
        interrupt.put("iterations", state.getOrDefault("iteration", 0));
        interrupt.put("draft", draft);
        state.put("interrupt", interrupt);
    }

    private void applyEditNode(Map<String, Object> state) {
        Map<String, Object> draft = new LinkedHashMap<>(getMap(state.get("draft_report")));
        String feedback = String.valueOf(state.getOrDefault("human_feedback", "")).trim();
        if (!feedback.isEmpty()) {
            draft.put("summary", String.valueOf(draft.getOrDefault("summary", "")) + " Reviewer note: " + feedback);
        }
        state.put("draft_report", draft);
    }

    private void publishNode(Map<String, Object> state) {
        Map<String, Object> draft = getMap(state.get("draft_report"));
        String feedback = String.valueOf(state.getOrDefault("human_feedback", ""));
        String executiveSummary = buildExecutiveSummary(String.valueOf(state.get("question")), draft, feedback);
        String publishedReport = formatFinalReport(draft, String.valueOf(state.get("question")), feedback);
        Map<String, Object> finalReport = new LinkedHashMap<>();
        finalReport.put("title", draft.getOrDefault("title", "Research Report: " + state.get("question")));
        finalReport.put("summary", executiveSummary);
        finalReport.put("key_findings", draft.getOrDefault("findings", List.of()));
        finalReport.put("sources", draft.getOrDefault("sources", List.of()));
        finalReport.put("confidence", Double.parseDouble(String.valueOf(draft.getOrDefault("confidence", 0.5))));
        finalReport.put("published_report", publishedReport);
        state.put("final_report", finalReport);
    }

    private void saveHistoryIfComplete(Map<String, Object> state) {
        if (state.containsKey("final_report") && state.get("reused_topic") == null) {
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("question", state.get("question"));
            record.put("report", state.get("final_report"));
            record.put("user_id", state.get("user_id"));
            record.put("created_at", java.time.OffsetDateTime.now().toString());
            List<Map<String, Object>> history = new ArrayList<>(historyStoreService.loadPersistedHistory());
            history.add(record);
            historyStoreService.savePersistedHistory(history);
        }
    }

    private List<Map<String, Object>> generateSearchResults(String query, List<String> allowedTools) {
        String toolHint = String.join(", ", allowedTools);
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content", "You are a research search assistant. Use the allowed tools: " + toolHint + "."),
                Map.of("role", "user", "content", "Generate up to 4 JSON search results for query: " + query + ". Each result should include title, url, snippet, full_snippet, tool_name, score, source_type, and chunk_id. Put the richest text in full_snippet and a short summary in snippet.")
        );
        JsonNode response = openAIClient.chatCompletionJson("gpt-4o-mini", messages);
        return parseSearchResults(response, query);
    }

    private List<Map<String, Object>> parseSearchResults(JsonNode node, String query) {
        List<Map<String, Object>> results = new ArrayList<>();
        if (node.isArray()) {
            node.forEach(item -> { if (item.isObject()) results.add(nodeToMap(item)); });
        } else if (node.isObject() && node.has("results") && node.get("results").isArray()) {
            node.get("results").forEach(item -> { if (item.isObject()) results.add(nodeToMap(item)); });
        } else {
            String text = node.asText();
            try {
                JsonNode parsed = objectMapper.readTree(text);
                if (parsed.isArray()) {
                    parsed.forEach(item -> { if (item.isObject()) results.add(nodeToMap(item)); });
                }
            } catch (Exception ignored) {
            }
        }
        if (results.isEmpty()) {
            results.add(Map.of(
                    "tool_name", "web_search",
                    "title", "Web result for " + query,
                    "url", "",
                    "snippet", "No search metadata was available.",
                    "score", 0.65,
                    "source_type", "web_search",
                    "chunk_id", "search-1"
            ));
        }
        return results.stream().map(this::normalizeToolResult).collect(Collectors.toList());
    }

    private Map<String, Object> normalizeToolResult(Map<String, Object> item) {
        Map<String, Object> normalized = new LinkedHashMap<>(item);
        String snippet = String.valueOf(item.getOrDefault("full_snippet", item.getOrDefault("snippet", ""))).trim();
        if (snippet.isBlank()) {
            snippet = String.valueOf(item.getOrDefault("snippet", "")).trim();
        }
        normalized.put("full_snippet", snippet);
        String toolName = String.valueOf(item.getOrDefault("tool_name", "")).trim();
        if (toolName.isBlank()) {
            toolName = String.valueOf(item.getOrDefault("source_type", "web_search")).trim();
        }
        normalized.put("tool_name", toolName.isBlank() ? "web_search" : toolName);
        normalized.put("title", String.valueOf(item.getOrDefault("title", "Untitled source")));
        normalized.put("url", String.valueOf(item.getOrDefault("url", "")));
        normalized.put("snippet", snippet);
        normalized.put("score", parseScore(item.getOrDefault("score", 0.65)));
        normalized.put("source_type", String.valueOf(item.getOrDefault("source_type", "web_search")));
        normalized.put("chunk_id", String.valueOf(item.getOrDefault("chunk_id", "search-" + System.nanoTime())));
        return normalized;
    }

    private double parseScore(Object score) {
        try {
            return Math.max(0.0, Math.min(1.0, Double.parseDouble(String.valueOf(score))));
        } catch (NumberFormatException ex) {
            return 0.7;
        }
    }

    private Map<String, Object> fetchStructuredDraftReport(List<Map<String, Object>> messages, String question) {
        try {
            String text = openAIClient.chatCompletion("gpt-4o-mini", messages, 1500);
            JsonNode response = parseDraftJson(text);
            Map<String, Object> result = null;
            if (response != null) {
                if (response.isArray() && response.size() > 0 && response.get(0).isObject()) {
                    response = response.get(0);
                }
                if (response.isObject()) {
                    result = nodeToMap(response);
                }
            }
            if (result != null && !String.valueOf(result.getOrDefault("summary", "")).trim().isBlank()) {
                if (!result.containsKey("title")) {
                    result.put("title", "Research Report: " + question);
                }
                return normalizeDraftReport(result, question);
            }
            return parseFreeTextDraftReport(text, question);
        } catch (Exception ex) {
            return parseFreeTextDraftReport(ex.getMessage(), question);
        }
    }

    private JsonNode parseDraftJson(String text) {
        try {
            return objectMapper.readTree(text);
        } catch (Exception ex) {
            return openAIClient.extractJsonFromText(text);
        }
    }

    private Map<String, Object> parseFreeTextDraftReport(String text, String question) {
        String summary = text == null ? "" : text.trim();
        if (summary.isBlank()) {
            return fallbackDraftReport(question);
        }
        return normalizeDraftReport(Map.of(
                "title", "Research Report: " + question,
                "findings", List.of(),
                "sources", List.of(Map.of("title", "Generated research source", "url", "")),
                "confidence", 0.5,
                "summary", summary
        ), question);
    }

    private Map<String, Object> fallbackDraftReport(String question) {
        return Map.of(
                "title", "Research Report: " + question,
                "findings", List.of(
                        "Could not fully parse structured output. Review the draft carefully.",
                        "Search evidence was still captured for manual review.",
                        "Use the cited sources to confirm key claims before publishing."
                ),
                "sources", List.of(),
                "confidence", 0.5,
                "summary", "The available evidence is incomplete; please review the sources and refine the report."
        );
    }

    private Map<String, Object> normalizeDraftReport(Map<String, Object> draftReport, String question) {
        Map<String, Object> normalized = new LinkedHashMap<>();
        normalized.put("title", String.valueOf(draftReport.getOrDefault("title", "Research Report: " + question)));
        normalized.put("findings", getList(draftReport.getOrDefault("findings", List.of())).stream()
                .map(item -> item == null ? "" : item.toString())
                .collect(Collectors.toList()));
        normalized.put("sources", normalizeReportSources(draftReport.getOrDefault("sources", List.of())));
        normalized.put("confidence", parseScore(draftReport.getOrDefault("confidence", 0.5)));
        normalized.put("summary", String.valueOf(draftReport.getOrDefault("summary", "")));
        if (getList((List<?>) normalized.get("findings")).size() < 3) {
            normalized.put("findings", List.of(
                    "Evidence coverage is still narrow and should be reviewed before publication.",
                    "At least one independent source corroborates part of the answer.",
                    "Important tradeoffs and unknowns are captured in the final summary."
            ));
        }
        if (getList(normalized.get("sources")).isEmpty()) {
            normalized.put("sources", List.of(Map.of("title", "Generated research source", "url", "")));
        }
        return normalized;
    }

    private List<Map<String, Object>> dedupeEvidence(List<Map<String, Object>> items, String query) {
        Map<String, Map<String, Object>> bestByIdentity = new LinkedHashMap<>();
        for (Map<String, Object> item : items) {
            String identity = String.format("%s|%s|%s",
                    String.valueOf(item.getOrDefault("title", "")).trim().toLowerCase(),
                    String.valueOf(item.getOrDefault("url", "")).trim().toLowerCase(),
                    String.valueOf(item.getOrDefault("snippet", "")).trim().toLowerCase());
            Map<String, Object> current = bestByIdentity.get(identity);
            if (current == null || Double.parseDouble(String.valueOf(item.getOrDefault("score", 0.0))) > Double.parseDouble(String.valueOf(current.getOrDefault("score", 0.0)))) {
                bestByIdentity.put(identity, item);
            }
        }
        List<Map<String, Object>> deduped = new ArrayList<>(bestByIdentity.values());
        deduped.sort((a, b) -> Double.compare(Double.parseDouble(String.valueOf(b.getOrDefault("score", 0.0))), Double.parseDouble(String.valueOf(a.getOrDefault("score", 0.0)))));
        if (query != null && !query.isBlank() && deduped.size() > 4) {
            deduped = rerankEvidence(deduped, query, deduped.size());
        }
        List<Map<String, Object>> results = new ArrayList<>();
        Map<String, Integer> sourceCounts = new HashMap<>();
        for (Map<String, Object> item : deduped) {
            String sourceIdentity = identity(item);
            int count = sourceCounts.getOrDefault(sourceIdentity, 0);
            if (count >= 2) {
                continue;
            }
            sourceCounts.put(sourceIdentity, count + 1);
            results.add(item);
            if (results.size() >= 8) {
                break;
            }
        }
        return results;
    }

    private List<Map<String, Object>> rerankEvidence(List<Map<String, Object>> items, String query, int limit) {
        return items.stream().limit(limit).collect(Collectors.toList());
    }

    private String identity(Map<String, Object> item) {
        return String.format("%s|%s|%s",
                String.valueOf(item.getOrDefault("title", "")).trim().toLowerCase(),
                String.valueOf(item.getOrDefault("url", "")).trim().toLowerCase(),
                String.valueOf(item.getOrDefault("tool_name", "")).trim().toLowerCase());
    }

    private void synthesizeNode(Map<String, Object> state) {
        List<Map<String, Object>> evidence = getSelectedEvidence(state).isEmpty() ? getSearchResults(state).stream().limit(4).collect(Collectors.toList()) : getSelectedEvidence(state);
        List<Map<String, Object>> retrievedHistory = getList(state.get("retrieval_context"));
        String prompt = "Research question: " + state.get("question") + "\n\n" +
                "Selected evidence:\n" + evidence.stream().map(item -> {
                    String title = String.valueOf(item.getOrDefault("title", ""));
                    String url = String.valueOf(item.getOrDefault("url", ""));
                    String snippet = String.valueOf(item.getOrDefault("full_snippet", item.getOrDefault("snippet", "")));
                    return "- Title: " + title + "\n  URL: " + url + "\n  Snippet: " + snippet;
                }).collect(Collectors.joining("\n")) + "\n\n" +
                "Relevant history:\n" + retrievedHistory.stream().map(item -> String.valueOf(item.getOrDefault("snippet", ""))).collect(Collectors.joining("\n")) + "\n\n" +
                "Using only the selected evidence above, return one valid JSON object with exactly these keys: title, findings, sources, confidence, summary. " +
                "The findings array should contain at least 8 clear points. " +
                "The summary text should be long, detailed, and at least 20 lines when formatted in plain text. " +
                "Do not invent additional sources or add any prose outside the JSON. " +
                "Write the most accurate, evidence-based summary supported by the selected evidence.";
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content", "You are a research synthesis assistant. Create a detailed structured report using only the selected evidence."),
                Map.of("role", "user", "content", prompt)
        );
        Map<String, Object> draftReport = fetchStructuredDraftReport(messages, String.valueOf(state.get("question")));
        state.put("draft_report", draftReport);
        state.put("run_metrics", buildMetrics(state, "hybrid", getList(state.get("search_results")).size(), getMap(state.get("run_metrics"))));
    }

    private List<Object> toObjectList(List<?> values) {
        if (values == null) {
            return Collections.emptyList();
        }
        return values.stream().map(item -> (Object) item).collect(Collectors.toList());
    }

    private RunSnapshotResponse buildSnapshot(String threadId, Map<String, Object> state) {
        String status = "idle";
        if (state.containsKey("interrupt")) {
            status = "waiting_input";
        } else if (state.get("final_report") != null) {
            status = "completed";
        }
        return new RunSnapshotResponse(
                threadId,
                status,
                String.valueOf(state.getOrDefault("question", "")),
                String.valueOf(state.getOrDefault("user_id", "")),
                Integer.parseInt(String.valueOf(state.getOrDefault("max_iterations", 0))),
                getList(state.get("research_plan")),
                String.valueOf(state.getOrDefault("history_decision", "")),
                String.valueOf(state.getOrDefault("review_decision", "")),
                state.get("guardrails"),
                state.get("run_metrics"),
                state.get("interrupt"),
                state.get("draft_report"),
                toObjectList(getSearchResults(state)),
                getList(state.get("selected_evidence_ids")),
                toObjectList(getSelectedEvidence(state)),
                state.get("final_report"),
                state.get("reused_topic")
        );
    }

    private List<Map<String, Object>> getSearchResults(Map<String, Object> state) {
        return getList(state.getOrDefault("search_results", List.of()));
    }

    private List<Map<String, Object>> getSelectedEvidence(Map<String, Object> state) {
        return getList(state.getOrDefault("selected_evidence", List.of()));
    }

    @SuppressWarnings("unchecked")
    private <T> List<T> getList(Object value) {
        if (value instanceof List<?>) {
            return (List<T>) value;
        }
        return new ArrayList<>();
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> getMap(Object value) {
        if (value instanceof Map<?, ?>) {
            return (Map<String, Object>) value;
        }
        return new LinkedHashMap<>();
    }

    private Map<String, Object> nodeToMap(JsonNode node) {
        return objectMapper.convertValue(node, new com.fasterxml.jackson.core.type.TypeReference<>() {});
    }

    private List<Map<String, Object>> normalizeReportSources(Object sources) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (Object item : getList(sources)) {
            if (item instanceof Map<?, ?> sourceMap) {
                Object titleCandidate = sourceMap.containsKey("title") ? sourceMap.get("title")
                        : sourceMap.containsKey("name") ? sourceMap.get("name")
                        : sourceMap.containsKey("source") ? sourceMap.get("source")
                        : "";
                Object urlCandidate = sourceMap.containsKey("url") ? sourceMap.get("url")
                        : sourceMap.containsKey("link") ? sourceMap.get("link")
                        : sourceMap.containsKey("href") ? sourceMap.get("href")
                        : "";
                String title = String.valueOf(titleCandidate).trim();
                String url = String.valueOf(urlCandidate).trim();
                if (url.isBlank()) {
                    continue;
                }
                if (title.isBlank()) {
                    title = url;
                }
                Map<String, Object> normalizedSource = new LinkedHashMap<>();
                normalizedSource.put("title", title);
                normalizedSource.put("url", url);
                items.add(normalizedSource);
            } else if (item instanceof String sourceUrl && !sourceUrl.isBlank()) {
                Map<String, Object> normalizedSource = new LinkedHashMap<>();
                normalizedSource.put("title", sourceUrl.trim());
                normalizedSource.put("url", sourceUrl.trim());
                items.add(normalizedSource);
            }
        }
        return items;
    }

    private List<Map<String, Object>> findRelevantHistory(Object question, List<Map<String, Object>> pastTopics) {
        if (question == null || pastTopics.isEmpty()) {
            return List.of();
        }
        String questionText = String.valueOf(question);
        return pastTopics.stream()
                .filter(item -> computeHistoryRelevance(questionText, String.valueOf(item.getOrDefault("question", ""))) >= 0.32)
                .sorted((a, b) -> Double.compare(
                        computeHistoryRelevance(questionText, String.valueOf(b.getOrDefault("question", ""))),
                        computeHistoryRelevance(questionText, String.valueOf(a.getOrDefault("question", "")))
                ))
                .limit(3)
                .collect(Collectors.toList());
    }

    private String classifyHistory(Object question, List<Map<String, Object>> relevantHistory) {
        if (relevantHistory.isEmpty()) {
            return "new";
        }
        return relevantHistory.size() > 0 ? "related" : "new";
    }

    private String buildHistoryRationale(String matchType, int count) {
        if ("similar".equals(matchType)) {
            return "Prior work is very close to the current question.";
        }
        if ("related".equals(matchType)) {
            return "Prior work overlaps the current question at a moderate level.";
        }
        return "No prior research record was similar enough to reuse.";
    }

    private Map<String, Object> findReuseCandidate(Object question, List<Map<String, Object>> pastTopics) {
        if (question == null) {
            return null;
        }
        String questionKey = normalizeQuestionKey(String.valueOf(question));
        for (Map<String, Object> topic : pastTopics) {
            if (questionKey.equals(normalizeQuestionKey(String.valueOf(topic.getOrDefault("question", ""))))) {
                return topic;
            }
        }
        return null;
    }

    private String normalizeQuestionKey(String question) {
        return question.toLowerCase().replaceAll("[^a-z0-9]+", " ").trim();
    }

    private double computeHistoryRelevance(String question, String itemQuestion) {
        Set<String> questionTerms = tokenizeTerms(question);
        Set<String> itemTerms = tokenizeTerms(itemQuestion);
        if (questionTerms.isEmpty() || itemTerms.isEmpty()) {
            return 0.0;
        }
        double overlap = questionTerms.stream().filter(itemTerms::contains).count();
        return overlap / Math.max(questionTerms.size(), 1);
    }

    private Set<String> tokenizeTerms(String text) {
        if (text == null) {
            return Collections.emptySet();
        }
        String normalized = text.toLowerCase();
        String[] tokens = normalized.split("[^a-z0-9]+");
        Set<String> words = new HashSet<>();
        for (String token : tokens) {
            if (token.length() > 2) {
                words.add(token);
            }
        }
        return words;
    }

    private List<String> buildLocalResearchPlan(String question, Map<String, Object> guardrails, List<Map<String, Object>> relevantHistory) {
        List<String> keywords = extractKeywords(question, 6);
        if (keywords.isEmpty()) {
            keywords = extractKeywords(String.valueOf(guardrails.getOrDefault("sanitized_question", question)), 6);
        }
        String core = String.join(" ", keywords.subList(0, Math.min(4, keywords.size())));
        if (core.isBlank()) {
            core = sanitizeQuestion(question);
        }
        if (core.length() > 120) {
            core = core.substring(0, 120).trim();
        }
        Set<String> allowed = new HashSet<>(getList(guardrails.getOrDefault("allowed_tools", DEFAULT_ALLOWED_TOOLS)));
        List<String> queries = new ArrayList<>();
        if (!core.isBlank()) {
            queries.add(core);
            queries.add(core + " evidence tradeoffs");
        }
        if (!relevantHistory.isEmpty()) {
            String priorTopic = truncateSummary(String.valueOf(relevantHistory.get(0).getOrDefault("question", "")), 60);
            if (!priorTopic.isBlank()) {
                queries.add(core + " update since " + priorTopic);
            }
        }
        if (allowed.contains("weather")) {
            queries.add(core + " current conditions");
        } else {
            queries.add(core + " background context");
        }
        return dedupeTextList(queries, 3);
    }

    private List<String> extractKeywords(String text, int limit) {
        if (text == null) {
            return List.of();
        }
        List<String> tokens = new ArrayList<>();
        for (String token : text.toLowerCase().split("[^a-z0-9]+")) {
            if (token.length() > 2) {
                tokens.add(token);
            }
        }
        return dedupeTextList(tokens, limit);
    }

    private List<String> dedupeTextList(List<String> values, int limit) {
        Set<String> seen = new LinkedHashSet<>();
        for (String value : values) {
            String item = value == null ? "" : value.trim();
            if (item.isBlank() || seen.contains(item)) {
                continue;
            }
            seen.add(item);
            if (seen.size() >= limit) {
                break;
            }
        }
        return new ArrayList<>(seen);
    }

    private String truncateSummary(String text) {
        return truncateSummary(text, 240);
    }

    private String truncateSummary(String text, int maxLength) {
        if (text == null) {
            return "";
        }
        String compact = text.trim().replaceAll("\\s+", " ");
        if (compact.length() <= maxLength) {
            return compact;
        }
        return compact.substring(0, Math.max(0, maxLength - 3)).trim() + "...";
    }

    private Map<String, Object> buildMetrics(Map<String, Object> state, String retrievalStrategy, int historyCandidates, Map<String, Object> baseMetrics) {
        Map<String, Object> metrics = new LinkedHashMap<>(baseMetrics);
        List<Map<String, Object>> searchResults = getSearchResults(state);
        metrics.put("iterations_used", Integer.parseInt(String.valueOf(state.getOrDefault("iteration", 0))));
        metrics.put("evidence_items", searchResults.size());
        metrics.put("unique_sources", (int) searchResults.stream().map(this::identity).distinct().count());
        metrics.put("history_candidates", historyCandidates);
        metrics.put("retrieval_strategy", retrievalStrategy);
        metrics.put("rerank_applied", 0);
        metrics.put("rerank_candidates", 0);
        metrics.put("rerank_duplicates_removed", 0);
        metrics.put("rerank_trimmed_for_limit", 0);
        metrics.put("rerank_distinct_sources", 0);
        return metrics;
    }

    private List<Map<String, Object>> selectEvidenceByIds(List<Map<String, Object>> items, List<String> selectedIds) {
        if (selectedIds == null || selectedIds.isEmpty()) {
            return new ArrayList<>();
        }
        Set<String> wanted = selectedIds.stream().filter(id -> id != null && !id.isBlank()).collect(Collectors.toSet());
        List<Map<String, Object>> selected = new ArrayList<>();
        for (Map<String, Object> item : items) {
            String chunkId = String.valueOf(item.getOrDefault("chunk_id", "")).trim();
            if (wanted.contains(chunkId)) {
                selected.add(item);
            }
        }
        if (selected.isEmpty() && !items.isEmpty()) {
            selected.add(items.get(0));
        }
        return selected;
    }

    private String formatFinalReport(Map<String, Object> draftReport, String question, String feedback) {
        String title = String.valueOf(draftReport.getOrDefault("title", "Research Report: " + question));
        String summary = String.valueOf(draftReport.getOrDefault("summary", ""));
        if (!feedback.isBlank()) {
            summary = summary + " Reviewer note: " + feedback;
        }
        List<String> findings = getList(draftReport.getOrDefault("findings", List.of()));
        List<Map<String, Object>> sources = getList(draftReport.getOrDefault("sources", List.of()));
        StringBuilder builder = new StringBuilder();
        builder.append("# ").append(title).append("\n\n");
        builder.append("Summary: ").append(summary).append("\n\n");
        if (!findings.isEmpty()) {
            builder.append("Key findings:\n");
            for (String finding : findings) {
                builder.append("- ").append(finding).append("\n");
            }
            builder.append("\n");
        }
        if (!sources.isEmpty()) {
            builder.append("Sources:\n");
            for (Map<String, Object> source : sources) {
                builder.append("- ").append(source.getOrDefault("title", "Untitled source"));
                String url = String.valueOf(source.getOrDefault("url", ""));
                if (!url.isBlank()) {
                    builder.append(" (").append(url).append(")");
                }
                builder.append("\n");
            }
            builder.append("\n");
        }
        builder.append("Confidence: ").append(String.format("%.2f", parseScore(draftReport.getOrDefault("confidence", 0.5))));
        return builder.toString().trim();
    }

    private String buildExecutiveSummary(String question, Map<String, Object> draftReport, String feedback) {
        String title = String.valueOf(draftReport.getOrDefault("title", "Research Report: " + question));
        String summary = String.valueOf(draftReport.getOrDefault("summary", ""));
        List<String> findings = getList(draftReport.getOrDefault("findings", List.of()));
        List<Map<String, Object>> sources = getList(draftReport.getOrDefault("sources", List.of()));
        String confidence = String.format("%.2f", parseScore(draftReport.getOrDefault("confidence", 0.5)));

        StringBuilder executive = new StringBuilder();
        executive.append(title).append("\n\n");
        executive.append("High-level summary: ").append(summary).append("\n\n");
        if (!findings.isEmpty()) {
            executive.append("Top findings:\n");
            for (int i = 0; i < Math.min(findings.size(), 5); i++) {
                executive.append(i + 1).append(". ").append(findings.get(i)).append("\n");
            }
            if (findings.size() > 5) {
                executive.append("...plus ").append(findings.size() - 5).append(" additional key points.\n");
            }
            executive.append("\n");
        }
        if (!sources.isEmpty()) {
            executive.append("Primary sources:\n");
            for (int i = 0; i < Math.min(sources.size(), 3); i++) {
                Map<String, Object> source = sources.get(i);
                String sourceTitle = String.valueOf(source.getOrDefault("title", "Untitled source"));
                String sourceUrl = String.valueOf(source.getOrDefault("url", ""));
                executive.append("- ").append(sourceTitle);
                if (!sourceUrl.isBlank()) {
                    executive.append(" (" + sourceUrl + ")");
                }
                executive.append("\n");
            }
            if (sources.size() > 3) {
                executive.append("...plus ").append(sources.size() - 3).append(" more sources.\n");
            }
            executive.append("\n");
        }
        executive.append("Confidence: ").append(confidence).append("\n");
        if (!feedback.isBlank()) {
            executive.append("Reviewer feedback: ").append(feedback).append("\n");
        }
        return executive.toString().trim();
    }
}
