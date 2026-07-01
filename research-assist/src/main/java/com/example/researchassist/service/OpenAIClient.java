package com.example.researchassist.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

@Service
public class OpenAIClient {

    private final String apiKey;
    private final String baseUrl;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public OpenAIClient(@Value("${openai.api.key:${OPENAI_API_KEY}:}") String apiKey,
                        @Value("${openai.api.base-url:${OPENAI_API_BASE_URL:https://api.openai.com/v1}}") String baseUrl) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("OPENAI_API_KEY or openai.api.key must be set in the environment or application properties before startup.");
        }
        this.apiKey = apiKey;
        this.baseUrl = baseUrl;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    public String chatCompletion(String model, List<Map<String, Object>> messages) {
        return chatCompletion(model, messages, 800);
    }

    public String chatCompletion(String model, List<Map<String, Object>> messages, int maxTokens) {
        Map<String, Object> body = Map.of(
                "model", model,
                "messages", messages,
                "temperature", 0.0,
                "max_tokens", maxTokens
        );
        JsonNode response = postJson("/chat/completions", body);
        JsonNode contentNode = response.path("choices").get(0).path("message").path("content");
        return contentNode.isTextual() ? contentNode.asText() : contentNode.toString();
    }

    public JsonNode chatCompletionJson(String model, List<Map<String, Object>> messages) {
        return chatCompletionJson(model, messages, 800);
    }

    public JsonNode chatCompletionJson(String model, List<Map<String, Object>> messages, int maxTokens) {
        String text = chatCompletion(model, messages, maxTokens);
        try {
            return objectMapper.readTree(text);
        } catch (JsonProcessingException ex) {
            JsonNode extracted = extractJsonFromText(text);
            if (extracted != null) {
                return extracted;
            }
            throw new IllegalStateException("Unable to parse structured response from OpenAI:\n" + text, ex);
        }
    }

    public JsonNode extractJsonFromText(String text) {
        String cleaned = removeCodeFences(text.trim());
        int startIndex = -1;
        char opening = 0;
        for (int i = 0; i < cleaned.length(); i++) {
            char c = cleaned.charAt(i);
            if (c == '{' || c == '[') {
                startIndex = i;
                opening = c;
                break;
            }
        }
        if (startIndex < 0) {
            return null;
        }
        char closing = opening == '{' ? '}' : ']';
        int depth = 0;
        boolean inString = false;
        boolean escaped = false;
        for (int i = startIndex; i < cleaned.length(); i++) {
            char c = cleaned.charAt(i);
            if (escaped) {
                escaped = false;
                continue;
            }
            if (c == '\\') {
                escaped = true;
                continue;
            }
            if (c == '"') {
                inString = !inString;
                continue;
            }
            if (inString) {
                continue;
            }
            if (c == opening) {
                depth++;
            } else if (c == closing) {
                depth--;
                if (depth == 0) {
                    String candidate = cleaned.substring(startIndex, i + 1);
                    try {
                        return objectMapper.readTree(candidate);
                    } catch (JsonProcessingException ignored) {
                        return null;
                    }
                }
            }
        }
        return null;
    }

    private String removeCodeFences(String text) {
        String cleaned = text.trim();
        if (cleaned.startsWith("```json")) {
            int fenceEnd = cleaned.indexOf("```", 7);
            if (fenceEnd >= 0) {
                return cleaned.substring(7, fenceEnd).trim();
            }
        }
        if (cleaned.startsWith("```")) {
            int fenceEnd = cleaned.indexOf("```", 3);
            if (fenceEnd >= 0) {
                return cleaned.substring(3, fenceEnd).trim();
            }
        }
        return cleaned;
    }

    public List<Double> embedTexts(String model, List<String> texts) {
        Map<String, Object> body = Map.of(
                "model", model,
                "input", texts
        );
        JsonNode response = postJson("/embeddings", body);
        return response.path("data").get(0).path("embedding").findValuesAsText("*").stream()
                .map(Double::valueOf)
                .toList();
    }

    private JsonNode postJson(String path, Object body) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("OPENAI_API_KEY is required for the Java workflow service.");
        }
        try {
            String requestBody = objectMapper.writeValueAsString(body);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + path))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(30))
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 300) {
                throw new IllegalStateException("OpenAI request failed: " + response.body());
            }
            return objectMapper.readTree(response.body());
        } catch (IOException | InterruptedException ex) {
            throw new RuntimeException("OpenAI request failed", ex);
        }
    }
}
