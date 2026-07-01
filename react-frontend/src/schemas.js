const nonEmptyString = { type: 'string', minLength: 1 }

const reportSourceSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['title', 'url'],
  properties: {
    title: nonEmptyString,
    url: { type: 'string' },
  },
}

const searchResultSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['tool_name', 'title', 'url', 'snippet', 'score', 'source_type', 'chunk_id'],
  properties: {
    tool_name: nonEmptyString,
    title: nonEmptyString,
    url: { type: 'string' },
    snippet: nonEmptyString,
    full_snippet: { type: 'string' },
    score: { type: 'number', minimum: 0, maximum: 1 },
    source_type: nonEmptyString,
    chunk_id: nonEmptyString,
  },
}

const selectedEvidenceSchema = searchResultSchema

const guardrailStateSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['sanitized_question', 'status', 'recommended_action', 'warnings', 'risk_flags', 'allowed_tools', 'explanation', 'clarifying_question'],
  properties: {
    sanitized_question: nonEmptyString,
    status: { enum: ['ready', 'needs_clarification', 'blocked'] },
    recommended_action: { enum: ['proceed', 'revise', 'block'] },
    warnings: { type: 'array', items: { type: 'string' } },
    risk_flags: {
      type: 'array',
      items: {
        enum: ['prompt_injection', 'secret_exfiltration', 'policy_bypass', 'overscoped_request', 'non_research_request'],
      },
    },
    allowed_tools: {
      type: 'array',
      items: { enum: ['tavily', 'wikipedia'] },
      minItems: 1,
      maxItems: 2,
    },
    explanation: nonEmptyString,
    clarifying_question: { type: 'string' },
  },
}

const runMetricsSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['iterations_used', 'evidence_items', 'unique_sources', 'history_candidates', 'retrieval_strategy', 'rerank_applied', 'rerank_candidates', 'rerank_duplicates_removed', 'rerank_trimmed_for_limit', 'rerank_distinct_sources'],
  properties: {
    iterations_used: { type: 'integer', minimum: 0 },
    evidence_items: { type: 'integer', minimum: 0 },
    unique_sources: { type: 'integer', minimum: 0 },
    history_candidates: { type: 'integer', minimum: 0 },
    retrieval_strategy: nonEmptyString,
    rerank_applied: { type: 'integer', minimum: 0, maximum: 1 },
    rerank_candidates: { type: 'integer', minimum: 0 },
    rerank_duplicates_removed: { type: 'integer', minimum: 0 },
    rerank_trimmed_for_limit: { type: 'integer', minimum: 0 },
    rerank_distinct_sources: { type: 'integer', minimum: 0 },
  },
}

const draftReportSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['title', 'findings', 'sources', 'confidence', 'summary'],
  properties: {
    title: nonEmptyString,
    findings: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: reportSourceSchema },
    confidence: { type: 'number', minimum: 0, maximum: 1 },
    summary: nonEmptyString,
  },
}

const finalReportSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['title', 'summary', 'key_findings', 'sources', 'confidence', 'published_report'],
  properties: {
    title: nonEmptyString,
    summary: nonEmptyString,
    key_findings: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: reportSourceSchema },
    confidence: { type: 'number', minimum: 0, maximum: 1 },
    published_report: nonEmptyString,
  },
}

const pastTopicSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['question', 'report', 'user_id', 'created_at'],
  properties: {
    question: nonEmptyString,
    report: finalReportSchema,
    user_id: nonEmptyString,
    created_at: nonEmptyString,
  },
}

const historyMatchSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['question', 'published_report', 'title', 'summary', 'user_id', 'created_at'],
  properties: {
    question: nonEmptyString,
    published_report: { type: 'string' },
    title: { type: 'string' },
    summary: { type: 'string' },
    user_id: { type: 'string' },
    created_at: { type: 'string' },
  },
}

const historyInterruptSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['action', 'current_question', 'match_type', 'rationale', 'matches', 'reuse_allowed', 'reuse_candidate'],
  properties: {
    action: { const: 'review_history_match' },
    current_question: nonEmptyString,
    match_type: { enum: ['similar', 'related', 'new'] },
    rationale: nonEmptyString,
    matches: { type: 'array', items: historyMatchSchema },
    reuse_allowed: { type: 'boolean' },
    reuse_candidate: { anyOf: [historyMatchSchema, { type: 'null' }] },
  },
}

const evidenceSelectionInterruptSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['action', 'question', 'research_plan', 'current_evidence', 'instructions'],
  properties: {
    action: { const: 'select_evidence_for_report' },
    question: nonEmptyString,
    research_plan: { type: 'array', items: { type: 'string' } },
    current_evidence: { type: 'array', items: searchResultSchema },
    instructions: nonEmptyString,
  },
}

const reviewInterruptSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['action', 'question', 'iterations', 'draft'],
  properties: {
    action: { const: 'review_before_publish' },
    question: nonEmptyString,
    iterations: { type: 'integer', minimum: 0 },
    draft: draftReportSchema,
  },
}

export const createSessionResponseSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['thread_id'],
  properties: {
    thread_id: nonEmptyString,
  },
}

export const startResearchRequestSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['thread_id', 'question', 'user_id', 'max_iterations'],
  properties: {
    thread_id: nonEmptyString,
    question: { type: 'string', minLength: 8, maxLength: 600 },
    user_id: nonEmptyString,
    max_iterations: { type: 'integer', minimum: 1, maximum: 6 },
  },
}

export const resumeResearchRequestSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['thread_id', 'decision', 'human_feedback'],
  properties: {
    thread_id: nonEmptyString,
    decision: {
      enum: [
        'proceed_with_context',
        'start_fresh_plan',
        'reuse_existing',
        'selected_evidence',
        'approved',
        'edited',
        'rejected',
      ],
    },
    selected_evidence_ids: { type: 'array', items: { type: 'string' } },
    human_feedback: { type: 'string', maxLength: 800 },
  },
}

export const runSnapshotResponseSchema = {
  type: 'object',
  additionalProperties: false,
  required: [
    'thread_id',
    'status',
    'question',
    'user_id',
    'max_iterations',
    'research_plan',
    'history_decision',
    'review_decision',
    'guardrails',
    'run_metrics',
    'interrupt',
    'draft_report',
    'search_results',
    'selected_evidence_ids',
    'selected_evidence',
    'final_report',
    'reused_topic',
  ],
  properties: {
    thread_id: nonEmptyString,
    status: { enum: ['idle', 'waiting_input', 'completed'] },
    question: { type: 'string' },
    user_id: { type: 'string' },
    max_iterations: { type: 'integer', minimum: 0 },
    research_plan: { type: 'array', items: { type: 'string' } },
    history_decision: { type: 'string' },
    review_decision: { type: 'string' },
    guardrails: {
      anyOf: [
        { type: 'null' },
        guardrailStateSchema,
      ],
    },
    run_metrics: {
      anyOf: [
        { type: 'null' },
        runMetricsSchema,
      ],
    },
    interrupt: {
      anyOf: [
        { type: 'null' },
        historyInterruptSchema,
        evidenceSelectionInterruptSchema,
        reviewInterruptSchema,
      ],
    },
    draft_report: {
      anyOf: [
        { type: 'null' },
        draftReportSchema,
      ],
    },
    search_results: { type: 'array', items: searchResultSchema },
    selected_evidence_ids: { type: 'array', items: { type: 'string' } },
    selected_evidence: { type: 'array', items: selectedEvidenceSchema },
    final_report: {
      anyOf: [
        { type: 'null' },
        finalReportSchema,
      ],
    },
    reused_topic: {
      anyOf: [
        { type: 'null' },
        pastTopicSchema,
      ],
    },
  },
}

export const translateTextRequestSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['text', 'target_language'],
  properties: {
    text: { type: 'string', minLength: 1, maxLength: 3200 },
    target_language: { type: 'string', minLength: 2, maxLength: 16 },
  },
}

export const translateTextResponseSchema = {
  type: 'object',
  additionalProperties: false,
  required: ['translated_text', 'target_language'],
  properties: {
    translated_text: nonEmptyString,
    target_language: { type: 'string', minLength: 2, maxLength: 16 },
  },
}
