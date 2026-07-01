package com.example.researchassist.controller;

import com.example.researchassist.model.BasicResponse;
import com.example.researchassist.model.CreateSessionResponse;
import com.example.researchassist.model.ResumeResearchRequest;
import com.example.researchassist.model.RunSnapshotResponse;
import com.example.researchassist.model.StartResearchRequest;
import com.example.researchassist.model.TranslateTextRequest;
import com.example.researchassist.model.TranslateTextResponse;
import com.example.researchassist.workflow.ResearchWorkflowService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api")
@Validated
public class ResearchController {

    private final ResearchWorkflowService workflowService;

    public ResearchController(ResearchWorkflowService workflowService) {
        this.workflowService = workflowService;
    }

    @GetMapping("/health")
    public ResponseEntity<BasicResponse> health() {
        return ResponseEntity.ok(new BasicResponse("ok"));
    }

    @PostMapping("/sessions")
    public ResponseEntity<CreateSessionResponse> createSession() {
        return ResponseEntity.ok(new CreateSessionResponse("ui-" + UUID.randomUUID().toString().replace("-", "")));
    }

    @PostMapping("/runs/start")
    public ResponseEntity<RunSnapshotResponse> startRun(@Valid @RequestBody StartResearchRequest request) {
        return ResponseEntity.ok(workflowService.startResearchRun(request));
    }

    @GetMapping("/runs/{threadId}")
    public ResponseEntity<RunSnapshotResponse> getRunSnapshot(@PathVariable String threadId) {
        return ResponseEntity.ok(workflowService.getRunSnapshot(threadId));
    }

    @PostMapping("/runs/resume")
    public ResponseEntity<RunSnapshotResponse> resumeRun(@Valid @RequestBody ResumeResearchRequest request) {
        return ResponseEntity.ok(workflowService.resumeResearchRun(request));
    }

    @PostMapping("/translate")
    public ResponseEntity<TranslateTextResponse> translateText(@Valid @RequestBody TranslateTextRequest request) {
        return ResponseEntity.ok(workflowService.translateText(request));
    }
}
