package com.example.researchassist.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class TavilyConfig {

    private final String apiKey;
    private final String apiUrl;

    public TavilyConfig(@Value("${tavily.api.key:${TAVILY_API_KEY}:}") String apiKey,
                        @Value("${tavily.api.base-url:${TAVILY_API_BASE_URL:https://api.tavily.ai/v1}}") String apiUrl) {
        this.apiKey = apiKey;
        this.apiUrl = apiUrl;
    }

    public boolean isEnabled() {
        return apiKey != null && !apiKey.isBlank();
    }

    public String getApiKey() {
        return apiKey;
    }

    public String getApiUrl() {
        return apiUrl;
    }
}
