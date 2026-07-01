package com.example.researchassist.model;

import jakarta.validation.constraints.NotBlank;

public record CreateSessionResponse(@NotBlank String threadId) {
}
