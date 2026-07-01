package com.example.researchassist.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class HistoryStoreService {

    private static final Path DATA_DIR = Path.of("research-assist", "data");
    private static final Path HISTORY_FILE = DATA_DIR.resolve("research_history.json");
    private final ObjectMapper objectMapper = new ObjectMapper();

    public List<Map<String, Object>> loadPersistedHistory() {
        if (!Files.exists(HISTORY_FILE)) {
            return Collections.emptyList();
        }
        try {
            return objectMapper.readValue(Files.readString(HISTORY_FILE), new TypeReference<>() {});
        } catch (IOException ex) {
            return Collections.emptyList();
        }
    }

    public void savePersistedHistory(List<Map<String, Object>> history) {
        try {
            Files.createDirectories(HISTORY_FILE.getParent());
            Path tempFile = HISTORY_FILE.resolveSibling(HISTORY_FILE.getFileName().toString() + ".tmp");
            Files.writeString(tempFile, objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(sortHistoryRecords(history)));
            Files.move(tempFile, HISTORY_FILE, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException ex) {
            throw new RuntimeException("Unable to persist research history", ex);
        }
    }

    public List<Map<String, Object>> mergeHistoryRecords(List<Map<String, Object>>... historySets) {
        List<Map<String, Object>> merged = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (List<Map<String, Object>> history : historySets) {
            if (history == null) {
                continue;
            }
            for (Map<String, Object> item : history) {
                if (item == null) {
                    continue;
                }
                String key = recordIdentity(item);
                if (seen.contains(key)) {
                    continue;
                }
                seen.add(key);
                merged.add(item);
            }
        }
        return sortHistoryRecords(merged);
    }

    public List<Map<String, Object>> sortHistoryRecords(List<Map<String, Object>> history) {
        if (history == null) {
            return Collections.emptyList();
        }
        return history.stream()
                .sorted((a, b) -> recordSortKey(b).compareTo(recordSortKey(a)))
                .collect(Collectors.toList());
    }

    private String recordIdentity(Map<String, Object> item) {
        return String.format("%s|%s", safeString(item.get("question")), safeString(item.get("created_at")));
    }

    private String recordSortKey(Map<String, Object> item) {
        return String.format("%s|%s", safeString(item.get("created_at")), safeString(item.get("question")).toLowerCase());
    }

    private String safeString(Object value) {
        return value == null ? "" : value.toString().trim();
    }
}
