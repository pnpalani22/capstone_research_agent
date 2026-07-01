package com.example.researchassist.model;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record TranslateTextRequest(
        @NotBlank @Size(min = 1, max = 3200) String text,
        @NotBlank @Size(min = 2, max = 16) String targetLanguage
) {
}
