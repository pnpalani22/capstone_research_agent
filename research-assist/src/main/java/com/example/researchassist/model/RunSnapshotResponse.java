package com.example.researchassist.model;

import java.util.List;

public record RunSnapshotResponse(
        String threadId,
        String status,
        String question,
        String userId,
        Integer maxIterations,
        List<String> researchPlan,
        String historyDecision,
        String reviewDecision,
        Object guardrails,
        Object runMetrics,
        Object interrupt,
        Object draftReport,
        List<Object> searchResults,
        List<String> selectedEvidenceIds,
        List<Object> selectedEvidence,
        Object finalReport,
        Object reusedTopic
) {
}
