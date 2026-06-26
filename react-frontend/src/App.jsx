import { useEffect, useState } from 'react'
import { createSession, resumeRun, startRun, translateText } from './api'

const languagePreferenceKey = 'research-ui-language'
const prosodyPreferenceKey = 'research-ui-prosody'
const recentLanguagesPreferenceKey = 'research-ui-recent-languages'

const languageOptions = [
  { code: 'en', label: 'English', voice: 'en-US', voiceFallbacks: ['en-GB', 'en'], helper: 'Original report voice for baseline playback.' },
  { code: 'es', label: 'Spanish', voice: 'es-ES', voiceFallbacks: ['es-MX', 'es-US', 'es'], helper: 'Good for broad international playback and demos.' },
  { code: 'fr', label: 'French', voice: 'fr-FR', voiceFallbacks: ['fr-CA', 'fr'], helper: 'Formal business tone with strong browser voice support.' },
  { code: 'de', label: 'German', voice: 'de-DE', voiceFallbacks: ['de'], helper: 'Clear technical phrasing for analytical summaries.' },
  { code: 'it', label: 'Italian', voice: 'it-IT', voiceFallbacks: ['it'], helper: 'Natural for conversational executive briefings.' },
  { code: 'pt', label: 'Portuguese', voice: 'pt-BR', voiceFallbacks: ['pt-PT', 'pt'], helper: 'Useful for LATAM-facing report playback.' },
  { code: 'hi', label: 'Hindi', voice: 'hi-IN', voiceFallbacks: ['hi'], helper: 'Good default for India-focused spoken delivery.' },
  { code: 'te', label: 'Telugu', voice: 'te-IN', voiceFallbacks: ['te'], helper: 'Regional output for Telugu-speaking audiences.' },
  { code: 'ta', label: 'Tamil', voice: 'ta-IN', voiceFallbacks: ['ta-SG', 'ta-LK', 'ta-MY', 'ta'], helper: 'Regional output for Tamil-speaking audiences.' },
  { code: 'bn', label: 'Bengali', voice: 'bn-IN', voiceFallbacks: ['bn-BD', 'bn'], helper: 'Adds coverage for Eastern India and Bangladesh contexts.' },
  { code: 'ja', label: 'Japanese', voice: 'ja-JP', voiceFallbacks: ['ja'], helper: 'Strong choice for concise product or research narration.' },
  { code: 'ko', label: 'Korean', voice: 'ko-KR', voiceFallbacks: ['ko'], helper: 'Useful for fast, structured technical updates.' },
  { code: 'ar', label: 'Arabic', voice: 'ar-SA', voiceFallbacks: ['ar-AE', 'ar-EG', 'ar'], helper: 'Expands playback support for MENA audiences.' },
  { code: 'ru', label: 'Russian', voice: 'ru-RU', voiceFallbacks: ['ru'], helper: 'Good for long-form analytical playback.' },
]

const languageGroups = [
  {
    label: 'Global Defaults',
    options: ['en'],
  },
  {
    label: 'Europe and Americas',
    options: ['es', 'fr', 'de', 'it', 'pt'],
  },
  {
    label: 'India and South Asia',
    options: ['hi', 'te', 'ta', 'bn'],
  },
  {
    label: 'East Asia',
    options: ['ja', 'ko'],
  },
  {
    label: 'Middle East and Eurasia',
    options: ['ar', 'ru'],
  },
]

const prosodyOptions = [
  { code: 'balanced', label: 'Balanced', rate: 1, pitch: 1, volume: 1, helper: 'Neutral delivery for most research answers.' },
  { code: 'calm', label: 'Calm', rate: 0.9, pitch: 0.92, volume: 0.96, helper: 'Softer and steadier for longer listening sessions.' },
  { code: 'clear', label: 'Clear', rate: 0.96, pitch: 1.08, volume: 1, helper: 'Sharper diction for precise technical explanations.' },
  { code: 'confident', label: 'Confident', rate: 1.02, pitch: 0.94, volume: 1, helper: 'Firm executive-style presentation tone.' },
  { code: 'friendly', label: 'Friendly', rate: 1, pitch: 1.14, volume: 1, helper: 'Warmer delivery for demos and non-technical audiences.' },
  { code: 'energetic', label: 'Energetic', rate: 1.08, pitch: 1.12, volume: 1, helper: 'Livelier voice for showcases or quick updates.' },
  { code: 'narration', label: 'Narration', rate: 0.84, pitch: 0.96, volume: 0.98, helper: 'Slower storytelling cadence for detailed summaries.' },
  { code: 'empathetic', label: 'Empathetic', rate: 0.92, pitch: 1.06, volume: 0.94, helper: 'Gentler tone for sensitive or explanatory content.' },
]

function readStoredPreference(key, allowedOptions, fallbackValue) {
  if (typeof window === 'undefined') {
    return fallbackValue
  }

  const storedValue = window.localStorage.getItem(key)
  if (storedValue && allowedOptions.some((option) => option.code === storedValue)) {
    return storedValue
  }

  return fallbackValue
}

function readStoredLanguageHistory() {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const storedValue = window.localStorage.getItem(recentLanguagesPreferenceKey)
    if (!storedValue) {
      return []
    }

    const parsedValue = JSON.parse(storedValue)
    if (!Array.isArray(parsedValue)) {
      return []
    }

    return parsedValue.filter((code) => languageOptions.some((option) => option.code === code)).slice(0, 5)
  } catch {
    return []
  }
}

function inferRecommendedProsody(text) {
  const normalizedText = String(text ?? '').trim()
  const textLength = normalizedText.length

  if (textLength >= 1400) {
    return 'narration'
  }

  if (textLength >= 900) {
    return 'calm'
  }

  if (textLength <= 240) {
    return 'confident'
  }

  if (/risk|incident|decline|concern|warning|sensitive/i.test(normalizedText)) {
    return 'empathetic'
  }

  if (/recommend|next step|action|priority|decision/i.test(normalizedText)) {
    return 'clear'
  }

  return 'balanced'
}

function selectMatchingVoice(voices, languageConfig) {
  const requestedTags = [languageConfig.voice, ...(languageConfig.voiceFallbacks ?? []), languageConfig.code]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase())

  if (!voices.length || !requestedTags.length) {
    return null
  }

  return voices.find((voice) => requestedTags.includes(String(voice.lang || '').toLowerCase()))
    ?? voices.find((voice) => requestedTags.some((tag) => String(voice.lang || '').toLowerCase().startsWith(tag)))
    ?? voices.find((voice) => requestedTags.some((tag) => tag.startsWith(String(voice.lang || '').toLowerCase())))
    ?? null
}

const defaultSnapshot = {
  thread_id: '',
  status: 'idle',
  question: '',
  user_id: '',
  max_iterations: 0,
  research_plan: [],
  history_decision: '',
  review_decision: '',
  guardrails: null,
  run_metrics: null,
  interrupt: null,
  draft_report: null,
  search_results: [],
  final_report: null,
  reused_topic: null,
}

function App() {
  const [userId, setUserId] = useState('analyst-1')
  const [maxIterations, setMaxIterations] = useState(3)
  const [question, setQuestion] = useState('')
  const [reviewerNote, setReviewerNote] = useState('')
  const [snapshot, setSnapshot] = useState(defaultSnapshot)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedLanguage, setSelectedLanguage] = useState(() => readStoredPreference(languagePreferenceKey, languageOptions, 'en'))
  const [translatedReport, setTranslatedReport] = useState('')
  const [translationLoading, setTranslationLoading] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [speakingLanguage, setSpeakingLanguage] = useState('')
  const [selectedProsody, setSelectedProsody] = useState(() => readStoredPreference(prosodyPreferenceKey, prosodyOptions, 'balanced'))
  const [recentLanguages, setRecentLanguages] = useState(() => readStoredLanguageHistory())
  const [isProsodyCustomized, setIsProsodyCustomized] = useState(false)
  const [availableVoices, setAvailableVoices] = useState([])
  const interrupt = snapshot.interrupt
  const finalReport = snapshot.final_report
  const draftReport = interrupt?.action === 'review_before_publish' ? interrupt.draft : snapshot.draft_report
  const evidence = snapshot.search_results ?? []
  const guardrails = snapshot.guardrails
  const metrics = snapshot.run_metrics
  const threadId = snapshot.thread_id
  const isReusedResult = snapshot.status === 'completed' && Boolean(finalReport) && Boolean(snapshot.reused_topic)
  const statusLabel = interrupt ? 'Awaiting analyst input' : finalReport ? 'Published' : loading ? 'Researching' : 'Ready'
  const stageLabel = interrupt?.action === 'review_history_match'
    ? 'History review'
    : interrupt?.action === 'review_before_publish'
      ? 'Draft approval'
      : finalReport
        ? 'Executive report'
        : snapshot.research_plan.length
          ? 'Evidence gathering'
          : 'Intake'
  const selectedLanguageMeta = languageOptions.find((option) => option.code === selectedLanguage) ?? languageOptions[0]
  const selectedProsodyMeta = prosodyOptions.find((option) => option.code === selectedProsody) ?? prosodyOptions[0]
  const reportSpeechText = selectedLanguage === 'en' ? finalReport?.published_report ?? '' : translatedReport
  const recommendedProsodyCode = inferRecommendedProsody(finalReport?.published_report ?? '')
  const recommendedProsodyMeta = prosodyOptions.find((option) => option.code === recommendedProsodyCode) ?? prosodyOptions[0]
  const groupedLanguageOptions = recentLanguages.length
    ? [{ label: 'Recently Used', options: recentLanguages }, ...languageGroups]
    : languageGroups
  const matchingVoice = selectMatchingVoice(availableVoices, selectedLanguageMeta)
  const hasMatchingVoice = Boolean(matchingVoice)
  const hasSpeechSynthesis = typeof window !== 'undefined' && 'speechSynthesis' in window
  const speechCapabilityByLanguage = languageOptions.reduce((capabilities, option) => {
    capabilities[option.code] = Boolean(selectMatchingVoice(availableVoices, option))
    return capabilities
  }, {})

  useEffect(() => {
    void initializeSession()
  }, [])

  useEffect(() => {
    setTranslatedReport('')
    setTranslationError('')
    window.speechSynthesis?.cancel()
    setSpeakingLanguage('')
  }, [snapshot.final_report?.published_report])

  useEffect(() => {
    return () => {
      window.speechSynthesis?.cancel()
    }
  }, [])

  useEffect(() => {
    if (!window.speechSynthesis) {
      return undefined
    }

    const updateVoices = () => {
      setAvailableVoices(window.speechSynthesis.getVoices())
    }

    updateVoices()
    window.speechSynthesis.addEventListener('voiceschanged', updateVoices)

    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', updateVoices)
    }
  }, [])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(languagePreferenceKey, selectedLanguage)
    }
  }, [selectedLanguage])

  useEffect(() => {
    setRecentLanguages((currentLanguages) => {
      const normalizedLanguages = [selectedLanguage, ...currentLanguages.filter((code) => code !== selectedLanguage)].slice(0, 5)
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(recentLanguagesPreferenceKey, JSON.stringify(normalizedLanguages))
      }

      return normalizedLanguages.join('|') === currentLanguages.join('|') ? currentLanguages : normalizedLanguages
    })
  }, [selectedLanguage])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(prosodyPreferenceKey, selectedProsody)
    }
  }, [selectedProsody])

  useEffect(() => {
    if (!finalReport?.published_report) {
      return
    }

    const recommendedProsody = inferRecommendedProsody(finalReport.published_report)
    if (!isProsodyCustomized) {
      setSelectedProsody(recommendedProsody)
    }
  }, [finalReport?.published_report, isProsodyCustomized])

  useEffect(() => {
    setTranslatedReport('')
    setTranslationError('')
    window.speechSynthesis?.cancel()
    setSpeakingLanguage('')
  }, [selectedLanguage])

  useEffect(() => {
    setIsProsodyCustomized(false)
  }, [snapshot.final_report?.published_report])

  useEffect(() => {
    if (!finalReport?.published_report) {
      return
    }

    if (selectedLanguage === 'en') {
      setTranslatedReport(finalReport.published_report)
      setTranslationError('')
      setTranslationLoading(false)
      return
    }

    let isActive = true

    async function syncTranslatedReport() {
      setTranslationLoading(true)
      setTranslationError('')

      try {
        const response = await translateText({
          text: finalReport.published_report,
          target_language: selectedLanguage,
        })
        if (!isActive) {
          return
        }
        setTranslatedReport(response.translated_text)
      } catch (translationRequestError) {
        if (!isActive) {
          return
        }
        setTranslationError(translationRequestError.message)
        setTranslatedReport('')
      } finally {
        if (isActive) {
          setTranslationLoading(false)
        }
      }
    }

    void syncTranslatedReport()

    return () => {
      isActive = false
    }
  }, [finalReport?.published_report, selectedLanguage])

  async function initializeSession() {
    setLoading(true)
    setError('')

    try {
      const session = await createSession()
      setSnapshot({ ...defaultSnapshot, thread_id: session.thread_id })
      setQuestion('')
      setReviewerNote('')
    } catch (sessionError) {
      setError(sessionError.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setSnapshot((currentSnapshot) => ({
      ...defaultSnapshot,
      thread_id: currentSnapshot.thread_id,
      question,
      user_id: userId,
      max_iterations: Number(maxIterations),
    }))

    try {
      const nextSnapshot = await startRun({
        thread_id: threadId,
        question,
        user_id: userId,
        max_iterations: Number(maxIterations),
      })
      setSnapshot(nextSnapshot)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleResume(decision) {
    setLoading(true)
    setError('')

    try {
      const nextSnapshot = await resumeRun({
        thread_id: threadId,
        decision,
        human_feedback: reviewerNote,
      })
      setSnapshot(nextSnapshot)
      if (decision === 'approved' || decision === 'edited' || decision === 'rejected') {
        setReviewerNote('')
      }
    } catch (resumeError) {
      setError(resumeError.message)
    } finally {
      setLoading(false)
    }
  }

  function handleSpeak(text, languageCode) {
    if (!text || !window.speechSynthesis) {
      return
    }

    const selectedOption = languageOptions.find((option) => option.code === languageCode)
    const prosody = prosodyOptions.find((option) => option.code === selectedProsody) ?? prosodyOptions[0]
    const utterance = new SpeechSynthesisUtterance(text)
    const voiceTag = selectedOption?.voice ?? selectedOption?.code ?? 'en-US'
    const matchedVoice = selectedOption ? selectMatchingVoice(availableVoices, selectedOption) : null

    utterance.lang = voiceTag
    utterance.rate = prosody.rate
    utterance.pitch = prosody.pitch
    utterance.volume = prosody.volume
    if (matchedVoice) {
      utterance.voice = matchedVoice
      utterance.lang = matchedVoice.lang
    }

    utterance.onend = () => setSpeakingLanguage('')
    utterance.onerror = () => setSpeakingLanguage('')

    window.speechSynthesis.cancel()
    setSpeakingLanguage(languageCode)
    window.speechSynthesis.speak(utterance)
  }

  function handleStopSpeech() {
    if (!window.speechSynthesis) {
      return
    }

    window.speechSynthesis.cancel()
    setSpeakingLanguage('')
  }

  return (
    <div className="shell">
      <header className="topbar panel">
        <h1>Enterprise Research Command Center</h1>
        <div className="topbar-meta">
          <div className="status-tile priority">
            <span>Workflow stage</span>
            <strong>{stageLabel}</strong>
          </div>
          <div className="status-tile">
            <span>Run status</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="status-tile wide">
            <span>Session</span>
            <strong>{threadId || 'Preparing workspace'}</strong>
          </div>
          <button type="button" className="ghost-button" onClick={() => void initializeSession()} disabled={loading}>
            Start new session
          </button>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className="sidebar-stack">
          <section className="panel intake-panel">
            <div className="section-heading">
              <p className="eyebrow">Intake</p>
              <h2>Research brief</h2>
            </div>
            <p className="section-intro">Use this panel to define the validation question, analyst identity, and search depth before the workflow starts.</p>
            <form className="intake-form" onSubmit={handleSubmit}>
              <label className="field-label" htmlFor="user-id">Analyst id</label>
              <input
                id="user-id"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
                placeholder="analyst-1"
              />

              <label className="field-label" htmlFor="depth">Research depth</label>
              <select
                id="depth"
                value={maxIterations}
                onChange={(event) => setMaxIterations(Number(event.target.value))}
              >
                <option value="2">Focused verification</option>
                <option value="3">Balanced investigation</option>
                <option value="5">Extended analysis</option>
                <option value="6">Maximum sweep</option>
              </select>

              <label className="field-label" htmlFor="question">Decision question</label>
              <textarea
                className="question-input"
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Example: How should an enterprise assistant combine retrieval, chunking, and evaluation guardrails to improve factual reliability?"
                rows={7}
              />
              <div className="field-meta-row">
                <p className="field-hint">Keep the brief focused on one decision, comparison, or measurable outcome.</p>
                <span className={`char-counter ${question.length > 540 ? 'danger' : question.length > 420 ? 'warning' : ''}`}>
                  {question.length}/600
                </span>
              </div>

              <button type="submit" className="primary-button" disabled={loading || !threadId}>
                {loading ? 'Running workflow...' : 'Launch research workflow'}
              </button>
            </form>
          </section>

          <section className="panel quality-panel">
            <div className="section-heading compact">
              <p className="eyebrow">Quality</p>
              <h3>Guardrails and controls</h3>
            </div>
            <p className="section-intro">This section explains whether the question is safe, complete, and eligible for the allowed research tools.</p>
            <div className="badge-row">
              <span className={`badge ${guardrails?.status === 'ready' ? 'success' : 'warning'}`}>
                {guardrails?.status ?? 'Not assessed'}
              </span>
              <span className="badge neutral">Iterations {maxIterations}</span>
            </div>
            <p className="muted-copy">
              {guardrails?.explanation || 'The platform will sanitize and assess the question before the search loop begins.'}
            </p>
            <p className="muted-copy">
              {guardrails?.sanitized_question || 'No sanitized question available yet.'}
            </p>
            <div className="stack-list">
              {(guardrails?.warnings?.length ? guardrails.warnings : ['No active warnings.']).map((item) => (
                <div className="list-card" key={item}>{item}</div>
              ))}
            </div>
            {guardrails?.allowed_tools?.length ? (
              <div className="inline-note">Allowed tools: {guardrails.allowed_tools.join(', ')}</div>
            ) : null}
            {guardrails?.status === 'blocked' && guardrails?.explanation?.includes('No allowed research tools') ? (
              <div className="inline-note danger">Tool access blocked by guardrail policy.</div>
            ) : null}
            {guardrails?.clarifying_question ? (
              <div className="inline-note">Clarify with: {guardrails.clarifying_question}</div>
            ) : null}
            {guardrails?.risk_flags?.length ? (
              <div className="inline-note danger">Risk flags: {guardrails.risk_flags.join(', ')}</div>
            ) : null}
          </section>

          <section className="panel metrics-panel">
            <div className="section-heading compact">
              <p className="eyebrow">Telemetry</p>
              <h3>Run instrumentation</h3>
            </div>
            <p className="section-intro">Track evidence volume, source diversity, rerank activity, and retrieval mode for validation runs.</p>
            <div className="metric-grid">
              <article className="metric-card">
                <span>Evidence items</span>
                <strong>{metrics?.evidence_items ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>Unique sources</span>
                <strong>{metrics?.unique_sources ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>History candidates</span>
                <strong>{metrics?.history_candidates ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>Retrieval mode</span>
                <strong>{metrics?.retrieval_strategy ?? 'lexical'}</strong>
              </article>
              <article className="metric-card">
                <span>Rerank applied</span>
                <strong>{metrics?.rerank_applied ? 'Yes' : 'No'}</strong>
              </article>
              <article className="metric-card">
                <span>Rerank candidates</span>
                <strong>{metrics?.rerank_candidates ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>Duplicates removed</span>
                <strong>{metrics?.rerank_duplicates_removed ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>Trimmed for limit</span>
                <strong>{metrics?.rerank_trimmed_for_limit ?? 0}</strong>
              </article>
              <article className="metric-card">
                <span>Distinct top sources</span>
                <strong>{metrics?.rerank_distinct_sources ?? 0}</strong>
              </article>
            </div>
          </section>
        </aside>

        <main className="main-stack">
          <section className="panel overview-panel">
            <div className="section-heading">
              <p className="eyebrow">Operating view</p>
              <h2>{snapshot.question || 'No active research brief yet'}</h2>
            </div>
            <p className="section-intro">This is the main status summary for the active validation query and where it currently sits in the workflow.</p>
            <div className="workflow-legend">
              <span className="legend-chip">1. Intake</span>
              <span className="legend-chip">2. Guardrails</span>
              <span className="legend-chip">3. Evidence</span>
              <span className="legend-chip">4. Review / Publish</span>
            </div>
            <div className="overview-grid">
              <article className="overview-card emphasis">
                <span>Research objective</span>
                <strong>{snapshot.question || 'Submit a brief to generate a structured research plan.'}</strong>
              </article>
              <article className="overview-card">
                <span>Planner output</span>
                <strong>{snapshot.research_plan.length ? `${snapshot.research_plan.length} targeted lines of inquiry` : 'Waiting for planner output'}</strong>
              </article>
              <article className="overview-card">
                <span>Review state</span>
                <strong>{interrupt ? 'Human checkpoint active' : finalReport ? 'Published and archived' : 'Automated workflow ready'}</strong>
              </article>
            </div>
          </section>

          <section className="panel blueprint-panel">
            <div className="section-heading compact">
              <p className="eyebrow">Plan</p>
              <h3>Research blueprint</h3>
            </div>
            <p className="section-intro">These are the generated search tracks that the agent will use to collect evidence.</p>
            {snapshot.research_plan.length ? (
              <div className="plan-list">
                {snapshot.research_plan.map((item, index) => (
                  <article className="plan-card" key={`${item}-${index}`}>
                    <span>Track {index + 1}</span>
                    <strong>{item}</strong>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted-copy">The planner will generate a small set of focused search directions after intake.</p>
            )}
          </section>

          {interrupt?.action === 'review_history_match' ? (
            <section className="panel decision-panel">
              <div className="section-heading compact">
                <p className="eyebrow">Checkpoint</p>
                <h3>Prior research overlap detected</h3>
              </div>
              <p className="section-intro">Choose whether to reuse prior work, build on it, or force a fresh validation run.</p>
              <p className="muted-copy">{interrupt.rationale}</p>
              <div className="history-grid">
                {interrupt.matches.map((match) => (
                  <article className="history-card" key={`${match.question}-${match.created_at}`}>
                    <span className="micro-label">{match.created_at || 'Stored research'}</span>
                    <h4>{match.title || 'Untitled report'}</h4>
                    <p><strong>Previous query:</strong> {match.question}</p>
                    <p>{match.summary || 'No summary available.'}</p>
                    <p className="subdued">{match.published_report || 'No published answer available.'}</p>
                  </article>
                ))}
              </div>
              <div className="button-row">
                <button type="button" className="primary-button" onClick={() => void handleResume('proceed_with_context')} disabled={loading}>
                  Use as context
                </button>
                <button type="button" className="secondary-button" onClick={() => void handleResume('start_fresh_plan')} disabled={loading}>
                  Start fresh
                </button>
                <button type="button" className="secondary-button" onClick={() => void handleResume('reuse_existing')} disabled={loading}>
                  Reuse best match
                </button>
              </div>
            </section>
          ) : null}

          {interrupt?.action === 'review_before_publish' ? (
            <section className="panel decision-panel">
              <div className="section-heading compact">
                <p className="eyebrow">Checkpoint</p>
                <h3>Draft approval required</h3>
              </div>
              <p className="section-intro">Review the synthesized answer, add feedback if needed, then approve, edit, or reject the draft.</p>
              <div className="review-grid">
                <article className="draft-summary-card">
                  <span className="micro-label">Draft summary</span>
                  <h4>{draftReport.title}</h4>
                  <p>{draftReport.summary}</p>
                  <div className="badge-row">
                    <span className="badge neutral">Iterations {interrupt.iterations}</span>
                    <span className="badge success">Confidence {Math.round(draftReport.confidence * 100)}%</span>
                  </div>
                </article>
                <article className="review-note-card">
                  <span className="micro-label">Reviewer note</span>
                  <textarea
                    rows={6}
                    value={reviewerNote}
                    onChange={(event) => setReviewerNote(event.target.value)}
                    placeholder="Add refinement notes for publishing or re-planning."
                  />
                </article>
              </div>
              <div className="two-column-grid">
                <article className="detail-card">
                  <h4>Key findings</h4>
                  <ul className="clean-list">
                    {draftReport.findings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </article>
                <article className="detail-card">
                  <h4>Sources</h4>
                  <ul className="clean-list">
                    {draftReport.sources.map((source) => (
                      <li key={`${source.title}-${source.url}`}>{source.title}{source.url ? ` | ${source.url}` : ''}</li>
                    ))}
                  </ul>
                </article>
              </div>
              <div className="button-row">
                <button type="button" className="primary-button" onClick={() => void handleResume('approved')} disabled={loading}>
                  Approve and publish
                </button>
                <button type="button" className="secondary-button" onClick={() => void handleResume('edited')} disabled={loading}>
                  Apply note and publish
                </button>
                <button type="button" className="secondary-button" onClick={() => void handleResume('rejected')} disabled={loading}>
                  Reject and re-plan
                </button>
              </div>
            </section>
          ) : null}

          <section className="panel evidence-panel">
            <div className="section-heading compact">
              <p className="eyebrow">Evidence</p>
              <h3>Normalized retrieval board</h3>
            </div>
            <p className="section-intro">Use this board to validate which tool produced the evidence, how it ranked, and whether the reranker kept diverse sources.</p>
            {evidence.length ? (
              <div className="evidence-grid">
                {evidence.slice(0, 8).map((item) => (
                  <article className="evidence-card" key={item.chunk_id}>
                    <div className="card-topline">
                      <span className="badge neutral">{item.source_type}</span>
                      <span className="score-pill">{Math.round(item.score * 100)}%</span>
                    </div>
                    <h4>{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}</h4>
                    <p>{item.snippet}</p>
                    <div className="micro-label">{item.tool_name}</div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted-copy">Evidence chunks from search tools and prior research memory will appear here.</p>
            )}
          </section>

          {finalReport ? (
            <section className="panel report-panel">
              <div className="section-heading">
                <p className="eyebrow">Output</p>
                <h2>{finalReport.title}</h2>
              </div>
              <p className="section-intro">This final section shows the published answer that should be checked against your validation expectation.</p>
              <div className="report-header-grid">
                <article className="report-status-card highlight">
                  <span>Executive summary</span>
                  <strong>{finalReport.summary}</strong>
                </article>
                <article className="report-status-card">
                  <span>Confidence</span>
                  <strong>{Math.round(finalReport.confidence * 100)}%</strong>
                </article>
                <article className="report-status-card">
                  <span>Publish mode</span>
                  <strong>{isReusedResult ? 'Reused institutional memory' : 'Fresh synthesis run'}</strong>
                </article>
              </div>
              {isReusedResult ? (
                <div className="inline-note success">Reused topic: {snapshot.reused_topic.question}</div>
              ) : null}
              <div className="two-column-grid">
                <article className="detail-card report-copy-card">
                  <div className="card-header-row">
                    <h4>Published answer</h4>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => handleSpeak(reportSpeechText || finalReport.published_report, selectedLanguage)}
                      aria-label={`Speak visible answer in ${selectedLanguageMeta.label}`}
                      title={`Speak visible answer in ${selectedLanguageMeta.label}`}
                      disabled={!hasSpeechSynthesis}
                    >
                      {speakingLanguage === selectedLanguage ? '■' : '🔊'}
                    </button>
                  </div>
                  <p className="published-copy">{finalReport.published_report}</p>
                </article>
                <article className="detail-card">
                  <h4>Source register</h4>
                  <ul className="clean-list">
                    {finalReport.sources.map((source) => (
                      <li key={`${source.title}-${source.url}`}>
                        {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a> : source.title}
                      </li>
                    ))}
                  </ul>
                </article>
              </div>
              <article className="detail-card translation-card">
                <div className="card-header-row">
                  <div>
                    <h4>Translation stage</h4>
                    <p className="muted-copy">Language selection updates the conversion body automatically, and the speech icons read exactly that visible converted content with the chosen tone.</p>
                  </div>
                  <div className="speech-action-row">
                    {reportSpeechText ? (
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() => handleSpeak(reportSpeechText, selectedLanguage)}
                        aria-label={`Speak answer in ${selectedLanguageMeta.label}`}
                        title={`Speak answer in ${selectedLanguageMeta.label}`}
                        disabled={!hasSpeechSynthesis}
                      >
                        🔊
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="icon-button stop-button"
                      onClick={handleStopSpeech}
                      aria-label="Stop speech playback"
                      title="Stop speech playback"
                      disabled={!speakingLanguage}
                    >
                      ■
                    </button>
                  </div>
                </div>
                <div className="translation-toolbar">
                  <div className="translation-control">
                    <label className="field-label" htmlFor="translation-language">Target language</label>
                    <select
                      id="translation-language"
                      value={selectedLanguage}
                      onChange={(event) => setSelectedLanguage(event.target.value)}
                    >
                      {groupedLanguageOptions.map((group) => (
                        <optgroup key={group.label} label={group.label}>
                          {group.options.map((optionCode) => {
                            const option = languageOptions.find((languageOption) => languageOption.code === optionCode)
                            if (!option) {
                              return null
                            }

                            const isSpeechSupported = Boolean(speechCapabilityByLanguage[option.code])
                            const optionLabel = group.label === 'Recently Used'
                              ? `${option.label} | recent | ${isSpeechSupported ? 'speech ready' : 'fallback speech'}`
                              : `${option.label} | ${isSpeechSupported ? 'speech ready' : 'fallback speech'}`

                            return <option key={`${group.label}-${option.code}`} value={option.code}>{optionLabel}</option>
                          })}
                        </optgroup>
                      ))}
                    </select>
                    <p className="control-helper">{selectedLanguageMeta.helper}</p>
                    {!hasMatchingVoice ? (
                      <p className="control-helper warning-helper">
                        No installed {selectedLanguageMeta.label} voice was detected in this browser. Playback will still try using browser fallback speech, but pronunciation may vary. Install a native {selectedLanguageMeta.label} voice for better accuracy.
                      </p>
                    ) : (
                      <p className="control-helper success-helper">
                        Voice ready: {matchingVoice?.name} ({matchingVoice?.lang})
                      </p>
                    )}
                  </div>
                  <div className="translation-control">
                    <label className="field-label" htmlFor="speech-prosody">Speech tone</label>
                    <select
                      id="speech-prosody"
                      value={selectedProsody}
                      onChange={(event) => {
                        setSelectedProsody(event.target.value)
                        setIsProsodyCustomized(true)
                      }}
                    >
                      {prosodyOptions.map((option) => (
                        <option key={option.code} value={option.code}>{option.label}</option>
                      ))}
                    </select>
                    <p className="control-helper">{selectedProsodyMeta.helper}</p>
                    <p className="control-helper accent-helper">
                      Recommended for this report: {recommendedProsodyMeta.label}
                      {isProsodyCustomized ? ' | manual override active' : ' | auto-applied'}
                    </p>
                  </div>
                </div>
                {translationError ? <p className="inline-note danger">{translationError}</p> : null}
                <div className="translated-copy-card">
                  <span className="micro-label">{selectedLanguageMeta.label} output | {selectedProsodyMeta.label} tone</span>
                  <p className="published-copy">
                    {translationLoading
                      ? `Updating the answer in ${selectedLanguageMeta.label}...`
                      : reportSpeechText || 'Select a language to update the answer preview and speech output.'}
                  </p>
                  <div className="selection-summary-row">
                    <span className="selection-pill">Language: {selectedLanguageMeta.label}</span>
                    <span className="selection-pill">Tone: {selectedProsodyMeta.label}</span>
                  </div>
                </div>
              </article>
              <article className="detail-card">
                <h4>Key findings</h4>
                <ul className="clean-list">
                  {finalReport.key_findings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </article>
            </section>
          ) : (
            <section className="panel empty-panel">
              <div className="section-heading compact">
                <p className="eyebrow">Workflow map</p>
                <h3>What the platform will do next</h3>
              </div>
              <p className="section-intro">This guide is shown before a report exists and explains the sequence that your validation query will follow.</p>
              <div className="workflow-strip">
                <article className="workflow-step active">
                  <span>1</span>
                  <strong>Assess question</strong>
                  <p>Sanitize the brief, apply guardrails, and load prior published work.</p>
                </article>
                <article className="workflow-step">
                  <span>2</span>
                  <strong>Retrieve evidence</strong>
                  <p>Blend history memory, Tavily search, and reference context into normalized chunks.</p>
                </article>
                <article className="workflow-step">
                  <span>3</span>
                  <strong>Review and publish</strong>
                  <p>Produce a draft, collect analyst input, and publish a final answer with cited sources.</p>
                </article>
              </div>
            </section>
          )}

          {error ? <section className="panel error-panel">{error}</section> : null}
        </main>
      </div>
    </div>
  )
}

export default App
