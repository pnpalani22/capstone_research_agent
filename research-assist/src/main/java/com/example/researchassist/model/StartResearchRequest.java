package com.example.researchassist.model;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record StartResearchRequest(
        @NotBlank String threadId,
        @NotBlank @Size(min = 8, max = 600) String question,
        @NotBlank String userId,
        @NotNull @Min(1) @Max(6) Integer maxIterations
) {
}
