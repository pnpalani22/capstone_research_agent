package com.example.researchassist.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public record ResumeResearchRequest(
        @NotBlank String threadId,
        @NotBlank String decision,
        @NotNull List<@Size(min = 1) String> selectedEvidenceIds,
        @Size(max = 800) String humanFeedback
) {
}
