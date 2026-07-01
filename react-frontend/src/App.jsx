import { useEffect, useRef, useState } from 'react'
import { createSession, resumeRun, startRun, translateText } from './api'

const languagePreferenceKey = 'research-ui-language'
const prosodyPreferenceKey = 'research-ui-prosody'
const voiceStylePreferenceKey = 'research-ui-voice-style'
const voiceSelectionPreferenceKey = 'research-ui-voice-selection'
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

const voiceStyleOptions = [
  { code: 'auto', label: 'Auto', helper: 'Use the closest installed voice for the selected language.' },
  { code: 'feminine', label: 'Female / Feminine', helper: 'Best-effort selection of a warmer, female-leaning installed voice.' },
  { code: 'masculine', label: 'Male / Masculine', helper: 'Best-effort selection of a deeper, male-leaning installed voice.' },
  { code: 'youthful', label: 'Youthful / Boyish', helper: 'Best-effort selection of a lighter, younger-sounding installed voice.' },
  { code: 'mature', label: 'Mature / Elder', helper: 'Best-effort selection of a more seasoned, narrator-like installed voice.' },
  { code: 'neutral', label: 'Neutral', helper: 'Prefer a steady, less character-driven installed voice.' },
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

function normalizeVoiceText(value) {
  return String(value ?? '').toLowerCase()
}

function scoreVoiceStyle(voice, styleCode) {
  const haystack = [
    voice.name,
    voice.voiceURI,
    voice.lang,
  ]
    .map(normalizeVoiceText)
    .join(' ')

  const styleKeywords = {
    feminine: ['female', 'woman', 'girl', 'samantha', 'victoria', 'zira', 'anna', 'emma', 'olivia', 'sophia', 'bella', 'nina', 'lisa', 'karen'],
    masculine: ['male', 'man', 'boy', 'david', 'daniel', 'george', 'michael', 'alex', 'john', 'tom', 'paul', 'mark', 'james', 'ryan'],
    youthful: ['youth', 'young', 'kid', 'teen', 'junior', 'boy', 'girl', 'child'],
    mature: ['mature', 'senior', 'elder', 'old', 'grand', 'narrator', 'professor'],
    neutral: ['neutral', 'standard', 'default'],
  }

  const keywords = styleKeywords[styleCode] ?? []
  if (!keywords.length) {
    return 0
  }

  return keywords.reduce((score, keyword) => score + (haystack.includes(keyword) ? 1 : 0), 0)
}

function selectStyledVoice(voices, languageConfig, styleCode) {
  if (!voices.length || !languageConfig) {
    return null
  }

  const languageMatches = voices.filter((voice) => {
    const requestedTags = [languageConfig.voice, ...(languageConfig.voiceFallbacks ?? []), languageConfig.code]
      .filter(Boolean)
      .map((value) => String(value).toLowerCase())
    const voiceLang = String(voice.lang || '').toLowerCase()
    return requestedTags.includes(voiceLang)
      || requestedTags.some((tag) => voiceLang.startsWith(tag))
      || requestedTags.some((tag) => tag.startsWith(voiceLang))
  })

  const basePool = languageMatches.length ? languageMatches : voices

  if (styleCode === 'auto') {
    return selectMatchingVoice(voices, languageConfig)
  }

  const ranked = [...basePool].sort((left, right) => scoreVoiceStyle(right, styleCode) - scoreVoiceStyle(left, styleCode))
  const bestStyledVoice = ranked.find((voice) => scoreVoiceStyle(voice, styleCode) > 0)
  return bestStyledVoice ?? selectMatchingVoice(basePool, languageConfig) ?? basePool[0] ?? null
}

function inferVoiceDescriptor(voice) {
  const name = normalizeVoiceText(voice?.name)
  const code = normalizeVoiceText(voice?.lang)
  const text = `${name} ${code}`

  if (/female|woman|girl|samantha|victoria|zira|anna|emma|olivia|sophia|bella|nina|lisa|karen/.test(text)) {
    return 'female'
  }
  if (/male|man|boy|david|daniel|george|michael|alex|john|tom|paul|mark|james|ryan/.test(text)) {
    return 'male'
  }
  if (/young|youth|kid|teen|junior|boy|girl|child/.test(text)) {
    return 'youthful'
  }
  if (/mature|senior|elder|old|grand|narrator|professor/.test(text)) {
    return 'mature'
  }
  return 'neutral'
}

function labelVoiceDescriptor(descriptor) {
  switch (descriptor) {
    case 'female':
      return 'Female / Feminine'
    case 'male':
      return 'Male / Masculine'
    case 'youthful':
      return 'Youthful / Boyish'
    case 'mature':
      return 'Mature / Elder'
    default:
      return 'Neutral'
  }
}

function voiceStyleCodeFromDescriptor(descriptor) {
  switch (descriptor) {
    case 'female':
      return 'feminine'
    case 'male':
      return 'masculine'
    case 'youthful':
      return 'youthful'
    case 'mature':
      return 'mature'
    default:
      return 'neutral'
  }
}

function formatVoiceLabel(voice) {
  const descriptor = inferVoiceDescriptor(voice)
  const name = voice?.name || 'Installed voice'
  const lang = voice?.lang ? ` (${voice.lang})` : ''
  return `${labelVoiceDescriptor(descriptor)} | ${name}${lang}`
}

function escapePdfText(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .replace(/[^\x20-\x7E\n\t]/g, '?')
    .replace(/\\/g, '\\\\')
    .replace(/\(/g, '\\(')
    .replace(/\)/g, '\\)')
    .replace(/\r/g, '')
}

function sanitizeFileName(value) {
  return String(value || 'research-report')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80) || 'research-report'
}

function wrapText(value, maxLength = 92) {
  const paragraphs = String(value ?? '').split(/\n+/)
  const wrappedLines = []

  paragraphs.forEach((paragraph) => {
    const words = paragraph.trim().split(/\s+/).filter(Boolean)
    if (!words.length) {
      wrappedLines.push('')
      return
    }

    let line = ''
    words.forEach((word) => {
      const nextLine = line ? `${line} ${word}` : word
      if (nextLine.length > maxLength && line) {
        wrappedLines.push(line)
        line = word
      } else {
        line = nextLine
      }
    })

    if (line) {
      wrappedLines.push(line)
    }
  })

  return wrappedLines
}

function buildReportPdfLines(report, snapshot, publishMode) {
  const sourceLines = report.sources?.length
    ? report.sources.map((source, index) => `${index + 1}. ${source.title}${source.url ? ` - ${source.url}` : ''}`)
    : ['No sources listed.']

  const findingLines = report.key_findings?.length
    ? report.key_findings.map((item, index) => `${index + 1}. ${item}`)
    : ['No key findings listed.']

  return [
    { text: report.title || 'Research Report', size: 18, bold: true, gapAfter: 10, wrap: 62 },
    { text: `Question: ${snapshot.question || 'Not available'}`, size: 10, gapAfter: 8, wrap: 88 },
    { text: `Confidence: ${Math.round((report.confidence ?? 0) * 100)}%`, size: 10, gapAfter: 4, wrap: 88 },
    { text: `Publish mode: ${publishMode}`, size: 10, gapAfter: 12, wrap: 88 },
    { text: 'Executive Summary', size: 13, bold: true, gapAfter: 5, wrap: 82 },
    { text: report.summary || 'No summary available.', size: 10, gapAfter: 12, wrap: 88 },
    { text: 'Published Answer', size: 13, bold: true, gapAfter: 5, wrap: 82 },
    { text: report.published_report || 'No published report available.', size: 10, gapAfter: 12, wrap: 88 },
    { text: 'Key Findings', size: 13, bold: true, gapAfter: 5, wrap: 82 },
    ...findingLines.map((text) => ({ text, size: 10, gapAfter: 4, wrap: 88 })),
    { text: '', size: 10, gapAfter: 8, wrap: 88 },
    { text: 'Sources', size: 13, bold: true, gapAfter: 5, wrap: 82 },
    ...sourceLines.map((text) => ({ text, size: 9, gapAfter: 4, wrap: 96 })),
  ]
}

function createReportPdfBlob(report, snapshot, publishMode) {
  const pageWidth = 612
  const pageHeight = 792
  const marginX = 54
  const marginTop = 58
  const marginBottom = 54
  const contentStartY = pageHeight - marginTop
  const minY = marginBottom
  const pages = [[]]
  let y = contentStartY

  const addLine = (text, size = 10, bold = false) => {
    const lineHeight = Math.max(12, size + 4)
    if (y - lineHeight < minY) {
      pages.push([])
      y = contentStartY
    }

    pages[pages.length - 1].push({ text, size, bold, x: marginX, y })
    y -= lineHeight
  }

  buildReportPdfLines(report, snapshot, publishMode).forEach((block) => {
    wrapText(block.text, block.wrap).forEach((line) => addLine(line, block.size, block.bold))
    y -= block.gapAfter ?? 0
  })

  const objects = []
  const addObject = (body) => {
    objects.push(body)
    return objects.length
  }

  const catalogId = addObject('<< /Type /Catalog /Pages 2 0 R >>')
  const pagesId = addObject('')
  const fontRegularId = addObject('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  const fontBoldId = addObject('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>')
  const pageIds = []

  pages.forEach((pageLines) => {
    const stream = pageLines.map((line) => (
      `BT /${line.bold ? 'F2' : 'F1'} ${line.size} Tf ${line.x} ${line.y} Td (${escapePdfText(line.text)}) Tj ET`
    )).join('\n')
    const streamLength = new TextEncoder().encode(stream).length
    const contentId = addObject(`<< /Length ${streamLength} >>\nstream\n${stream}\nendstream`)
    const pageId = addObject(`<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 ${fontRegularId} 0 R /F2 ${fontBoldId} 0 R >> >> /Contents ${contentId} 0 R >>`)
    pageIds.push(pageId)
  })

  objects[pagesId - 1] = `<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(' ')}] /Count ${pageIds.length} >>`

  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  objects.forEach((body, index) => {
    offsets.push(pdf.length)
    pdf += `${index + 1} 0 obj\n${body}\nendobj\n`
  })

  const xrefOffset = pdf.length
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  offsets.slice(1).forEach((offset) => {
    pdf += `${String(offset).padStart(10, '0')} 00000 n \n`
  })
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root ${catalogId} 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`

  return new Blob([new TextEncoder().encode(pdf)], { type: 'application/pdf' })
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
  selected_evidence_ids: [],
  selected_evidence: [],
  final_report: null,
  reused_topic: null,
}

const FATAL_API_ERROR_MESSAGE = 'The research service stopped because the API quota or token limit was reached. Please check your OpenAI usage or billing, then reload the app after it is restored.'

function isFatalApiError(error) {
  const status = Number(error?.status ?? 0)
  const message = String(error?.message ?? '').toLowerCase()
  return status === 503
    || /insufficient_quota|quota|token limit|maximum context length|context length|rate limit/.test(message)
}

function formatApiError(error) {
  if (isFatalApiError(error)) {
    return FATAL_API_ERROR_MESSAGE
  }

  return String(error?.message ?? 'Request failed')
}

function App() {
  const [userId, setUserId] = useState('analyst-1')
  const [maxIterations, setMaxIterations] = useState(3)
  const [question, setQuestion] = useState('')
  const [reviewerNote, setReviewerNote] = useState('')
  const [snapshot, setSnapshot] = useState(defaultSnapshot)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [fatalError, setFatalError] = useState('')
  const [selectedLanguage, setSelectedLanguage] = useState(() => readStoredPreference(languagePreferenceKey, languageOptions, 'en'))
  const [translatedReport, setTranslatedReport] = useState('')
  const [translationLoading, setTranslationLoading] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [speakingLanguage, setSpeakingLanguage] = useState('')
  const [selectedProsody, setSelectedProsody] = useState(() => readStoredPreference(prosodyPreferenceKey, prosodyOptions, 'balanced'))
  const [selectedVoiceStyle, setSelectedVoiceStyle] = useState(() => readStoredPreference(voiceStylePreferenceKey, voiceStyleOptions, 'auto'))
  const [selectedVoiceURI, setSelectedVoiceURI] = useState(() => {
    if (typeof window === 'undefined') {
      return ''
    }

    return window.localStorage.getItem(voiceSelectionPreferenceKey) || ''
  })
  const [voiceSearchQuery, setVoiceSearchQuery] = useState('')
  const [recentLanguages, setRecentLanguages] = useState(() => readStoredLanguageHistory())
  const [isProsodyCustomized, setIsProsodyCustomized] = useState(false)
  const [availableVoices, setAvailableVoices] = useState([])
  const [reportPreviewOpen, setReportPreviewOpen] = useState(false)
  const [selectedEvidenceId, setSelectedEvidenceId] = useState('')
  const activeUtteranceRef = useRef(null)
  const stopSpeechRequestedRef = useRef(false)
  const autoResumeHistoryRef = useRef(false)
  const interrupt = snapshot.interrupt
  const finalReport = snapshot.final_report
  const draftReport = interrupt?.action === 'review_before_publish' ? interrupt.draft : snapshot.draft_report
  const evidence = snapshot.search_results ?? []
  const evidenceSelectionInterrupt = interrupt?.action === 'select_evidence_for_report' ? interrupt : null
  const evidenceSelectionItems = evidenceSelectionInterrupt?.current_evidence?.length ? evidenceSelectionInterrupt.current_evidence : evidence.slice(0, 8)
  const selectedEvidenceItem = evidenceSelectionItems.find((item) => item.chunk_id === selectedEvidenceId) ?? null
  const guardrails = snapshot.guardrails
  const metrics = snapshot.run_metrics
  const threadId = snapshot.thread_id
  const isReusedResult = snapshot.status === 'completed' && Boolean(finalReport) && Boolean(snapshot.reused_topic)
  const statusLabel = interrupt ? 'Awaiting analyst input' : finalReport ? 'Published' : loading ? 'Researching' : 'Ready'
  const stageLabel = interrupt?.action === 'review_history_match'
    ? 'History review'
    : interrupt?.action === 'select_evidence_for_report'
      ? 'Evidence selection'
    : interrupt?.action === 'review_before_publish'
      ? 'Draft approval'
      : finalReport
        ? 'Executive report'
        : snapshot.research_plan.length
          ? 'Evidence gathering'
          : 'Intake'
  const selectedLanguageMeta = languageOptions.find((option) => option.code === selectedLanguage) ?? languageOptions[0]
  const selectedProsodyMeta = prosodyOptions.find((option) => option.code === selectedProsody) ?? prosodyOptions[0]
  const selectedVoiceStyleMeta = voiceStyleOptions.find((option) => option.code === selectedVoiceStyle) ?? voiceStyleOptions[0]
  const reportSpeechText = selectedLanguage === 'en' ? finalReport?.published_report ?? '' : translatedReport
  const recommendedProsodyCode = inferRecommendedProsody(finalReport?.published_report ?? '')
  const recommendedProsodyMeta = prosodyOptions.find((option) => option.code === recommendedProsodyCode) ?? prosodyOptions[0]
  const groupedLanguageOptions = recentLanguages.length
    ? [{ label: 'Recently Used', options: recentLanguages }, ...languageGroups]
    : languageGroups
  const matchingVoice = selectMatchingVoice(availableVoices, selectedLanguageMeta)
  const hasMatchingVoice = Boolean(matchingVoice)
  const hasSpeechSynthesis = typeof window !== 'undefined' && 'speechSynthesis' in window
  const finalReportPublishMode = isReusedResult ? 'Reused institutional memory' : 'Fresh synthesis run'
  const visibleVoiceOptions = availableVoices
    .filter((voice) => {
      const requestedTags = [selectedLanguageMeta.voice, ...(selectedLanguageMeta.voiceFallbacks ?? []), selectedLanguageMeta.code]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase())
      const voiceLang = String(voice.lang || '').toLowerCase()
      return requestedTags.includes(voiceLang)
        || requestedTags.some((tag) => voiceLang.startsWith(tag))
        || requestedTags.some((tag) => tag.startsWith(voiceLang))
    })
    .map((voice) => ({
      ...voice,
      descriptor: inferVoiceDescriptor(voice),
      label: formatVoiceLabel(voice),
    }))
  const filteredVoiceOptions = visibleVoiceOptions.filter((voice) => {
    const query = normalizeVoiceText(voiceSearchQuery).trim()
    if (!query) {
      return true
    }

    return [
      voice.name,
      voice.voiceURI,
      voice.lang,
      voice.descriptor,
      voice.label,
    ]
      .map(normalizeVoiceText)
      .some((item) => item.includes(query))
  })
  const groupedVoiceOptions = [
    { label: 'Female / Feminine', voices: filteredVoiceOptions.filter((voice) => voice.descriptor === 'female') },
    { label: 'Male / Masculine', voices: filteredVoiceOptions.filter((voice) => voice.descriptor === 'male') },
    { label: 'Youthful / Boyish', voices: filteredVoiceOptions.filter((voice) => voice.descriptor === 'youthful') },
    { label: 'Mature / Elder', voices: filteredVoiceOptions.filter((voice) => voice.descriptor === 'mature') },
    { label: 'Neutral', voices: filteredVoiceOptions.filter((voice) => voice.descriptor === 'neutral') },
  ].filter((group) => group.voices.length)
  const selectedVoiceOption = visibleVoiceOptions.find((voice) => voice.voiceURI === selectedVoiceURI) ?? null
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
    setReportPreviewOpen(false)
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
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(voiceStylePreferenceKey, selectedVoiceStyle)
    }
  }, [selectedVoiceStyle])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(voiceSelectionPreferenceKey, selectedVoiceURI)
    }
  }, [selectedVoiceURI])

  useEffect(() => {
    if (!interrupt || !autoResumeHistoryRef.current) {
      return
    }

    if (interrupt.action === 'review_history_match' && !interrupt.reuse_allowed) {
      void handleResume('proceed_with_context')
      autoResumeHistoryRef.current = false
    }
  }, [interrupt?.action, interrupt?.reuse_allowed])

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
    if (!visibleVoiceOptions.length) {
      return
    }

    if (!selectedVoiceURI || !visibleVoiceOptions.some((voice) => voice.voiceURI === selectedVoiceURI)) {
      const bestVoice = selectStyledVoice(visibleVoiceOptions, selectedLanguageMeta, selectedVoiceStyle)
      if (bestVoice?.voiceURI) {
        setSelectedVoiceURI(bestVoice.voiceURI)
      }
    }
  }, [visibleVoiceOptions, selectedLanguageMeta, selectedVoiceStyle, selectedVoiceURI])

  useEffect(() => {
    if (evidenceSelectionInterrupt) {
      setSelectedEvidenceId('')
      return
    }

    setSelectedEvidenceId('')
  }, [evidenceSelectionInterrupt?.action, interrupt?.action])

  async function handleTranslate() {
    if (!finalReport?.published_report) {
      return
    }

    setTranslationLoading(true)
    setTranslationError('')

    try {
      if (selectedLanguage === 'en') {
        setTranslatedReport(finalReport.published_report)
        return
      }

      const response = await translateText({
        text: finalReport.published_report,
        target_language: selectedLanguage,
      })
      setTranslatedReport(response.translated_text)
    } catch (translationRequestError) {
      const message = formatApiError(translationRequestError)
      if (isFatalApiError(translationRequestError)) {
        setFatalError(message)
        setError('')
        setTranslationError('')
        setTranslatedReport('')
        return
      }
      setTranslationError(message)
      setTranslatedReport('')
    } finally {
      setTranslationLoading(false)
    }
  }

  async function initializeSession() {
    setLoading(true)
    setError('')

    try {
      const session = await createSession()
      setSnapshot({ ...defaultSnapshot, thread_id: session.thread_id })
      setQuestion('')
      setReviewerNote('')
    } catch (sessionError) {
      const message = formatApiError(sessionError)
      if (isFatalApiError(sessionError)) {
        setFatalError(message)
        setError('')
        return
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError('')

    const session = await createSession()
    const effectiveThreadId = session.thread_id
    autoResumeHistoryRef.current = true
    setSnapshot({ ...defaultSnapshot, thread_id: effectiveThreadId })

    try {
      const nextSnapshot = await startRun({
        thread_id: effectiveThreadId,
        question,
        user_id: userId,
        max_iterations: Number(maxIterations),
      })
      setSnapshot(nextSnapshot)
    } catch (submitError) {
      const message = formatApiError(submitError)
      if (isFatalApiError(submitError)) {
        setFatalError(message)
        setError('')
        return
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  async function handleResume(decision, options = {}) {
    setLoading(true)
    setError('')

    try {
      const nextSnapshot = await resumeRun({
        thread_id: threadId,
        decision,
        human_feedback: reviewerNote,
        selected_evidence_ids: options.selectedEvidenceIds ?? [],
      })
      setSnapshot(nextSnapshot)
      if (decision === 'approved' || decision === 'edited' || decision === 'rejected') {
        setReviewerNote('')
      }
    } catch (resumeError) {
      const message = formatApiError(resumeError)
      if (isFatalApiError(resumeError)) {
        setFatalError(message)
        setError('')
        return
      }
      setError(message)
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
    const voiceStyle = voiceStyleOptions.find((option) => option.code === selectedVoiceStyle) ?? voiceStyleOptions[0]
    const utterance = new SpeechSynthesisUtterance(text)
    const voiceTag = selectedOption?.voice ?? selectedOption?.code ?? 'en-US'
    const exactVoice = availableVoices.find((voice) => voice.voiceURI === selectedVoiceURI) ?? null
    const matchedVoice = exactVoice ?? (selectedOption ? selectStyledVoice(availableVoices, selectedOption, voiceStyle.code) : null)

    utterance.lang = voiceTag
    utterance.rate = prosody.rate
    utterance.pitch = prosody.pitch
    utterance.volume = prosody.volume
    if (matchedVoice) {
      utterance.voice = matchedVoice
      utterance.lang = matchedVoice.lang
    }

    utterance.onend = () => {
      if (!stopSpeechRequestedRef.current) {
        setSpeakingLanguage('')
      }
      activeUtteranceRef.current = null
    }
    utterance.onerror = () => {
      activeUtteranceRef.current = null
      setSpeakingLanguage('')
    }

    stopSpeechRequestedRef.current = false
    activeUtteranceRef.current = utterance
    window.speechSynthesis.cancel()
    setSpeakingLanguage(languageCode)
    window.speechSynthesis.speak(utterance)
  }

  function handleSelectEvidence(item) {
    setSelectedEvidenceId(item?.chunk_id ?? '')
  }

  function handleStopSpeech() {
    if (!window.speechSynthesis) {
      return
    }

    stopSpeechRequestedRef.current = true
    activeUtteranceRef.current = null
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.pause()
    }
    window.speechSynthesis.cancel()
    setSpeakingLanguage('')
  }

  function handleVoiceSelection(nextVoiceURI) {
    setSelectedVoiceURI(nextVoiceURI)
    const matching = visibleVoiceOptions.find((voice) => voice.voiceURI === nextVoiceURI)
    if (matching) {
      setSelectedVoiceStyle(voiceStyleCodeFromDescriptor(inferVoiceDescriptor(matching)))
    }
  }

  function handleDownloadReportPdf() {
    if (!finalReport) {
      return
    }

    const pdfBlob = createReportPdfBlob(finalReport, snapshot, finalReportPublishMode)
    const downloadUrl = URL.createObjectURL(pdfBlob)
    const downloadLink = document.createElement('a')
    downloadLink.href = downloadUrl
    downloadLink.download = `${sanitizeFileName(finalReport.title)}.pdf`
    document.body.appendChild(downloadLink)
    downloadLink.click()
    downloadLink.remove()
    URL.revokeObjectURL(downloadUrl)
  }

  if (fatalError) {
    return (
      <div className="shell">
        <main className="panel fatal-panel" style={{ maxWidth: '720px', margin: '6rem auto' }}>
          <p className="eyebrow">Session ended</p>
          <h1>Research workflow stopped</h1>
          <p className="section-intro">{fatalError}</p>
          <div className="button-row">
            <button type="button" className="primary-button" onClick={() => window.location.reload()}>
              Reload app
            </button>
          </div>
        </main>
      </div>
    )
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

          {interrupt?.action === 'review_history_match' && interrupt.reuse_allowed ? (
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
                {interrupt.reuse_allowed ? (
                  <button type="button" className="secondary-button" onClick={() => void handleResume('reuse_existing')} disabled={loading}>
                    Reuse exact match
                  </button>
                ) : null}
              </div>
              <p className="inline-note">Reuse is limited to the newest exact question match.</p>
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
            <p className="section-intro">
              {evidenceSelectionInterrupt
                ? 'Choose the evidence items that should drive the report, then continue with the selected set.'
                : 'Use this board to validate which tool produced the evidence, how it ranked, and whether the reranker kept diverse sources.'}
            </p>
            {evidence.length ? (
              <div className="evidence-workspace">
                <div className="evidence-grid">
                  {evidenceSelectionItems.map((item) => {
                    const isSelected = selectedEvidenceId === item.chunk_id
                    return (
                      <article
                        className={`evidence-card ${isSelected ? 'selected' : ''}`}
                        key={item.chunk_id}
                        onClick={() => handleSelectEvidence(item)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            handleSelectEvidence(item)
                          }
                        }}
                        aria-pressed={isSelected}
                      >
                        <div className="card-topline">
                          <span className="badge neutral">{item.source_type}</span>
                          <span className="score-pill">{Math.round(item.score * 100)}%</span>
                        </div>
                        <h4>{item.url ? <a href={item.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>{item.title}</a> : item.title}</h4>
                        <p>{item.full_snippet?.trim() ? item.full_snippet : item.snippet}</p>
                        <div className="micro-label">{item.tool_name}</div>
                      </article>
                    )
                  })}
                </div>
                {evidenceSelectionInterrupt ? (
                  <aside className="evidence-drawer">
                    <div className="section-heading compact">
                      <p className="eyebrow">Details</p>
                      <h4>{selectedEvidenceItem?.title || 'Select evidence'}</h4>
                    </div>
                    {selectedEvidenceItem ? (
                      <>
                        <p className="muted-copy">{selectedEvidenceItem.full_snippet?.trim() ? selectedEvidenceItem.full_snippet : selectedEvidenceItem.snippet}</p>
                        <div className="selection-summary-row">
                          <span className="selection-pill">{selectedEvidenceItem.tool_name}</span>
                          <span className="selection-pill">{selectedEvidenceItem.source_type}</span>
                          <span className="selection-pill">{Math.round(selectedEvidenceItem.score * 100)}%</span>
                        </div>
                        <p className="detail-meta"><strong>Chunk:</strong> {selectedEvidenceItem.chunk_id}</p>
                        {selectedEvidenceItem.url ? (
                          <p className="detail-meta">
                            <strong>Source:</strong>{' '}
                            <a href={selectedEvidenceItem.url} target="_blank" rel="noreferrer">
                              Open source
                            </a>
                          </p>
                        ) : null}
                        <div className="button-row compact-row">
                          <button
                            type="button"
                            className="primary-button"
                            onClick={() => void handleResume('selected_evidence', { selectedEvidenceIds: [selectedEvidenceItem.chunk_id] })}
                            disabled={loading}
                          >
                            Use selected evidence and continue
                          </button>
                        </div>
                      </>
                    ) : (
                      <p className="muted-copy">{evidenceSelectionInterrupt.instructions}</p>
                    )}
                  </aside>
                ) : null}
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
              <div className="report-action-row" aria-label="Final report PDF actions">
                <button type="button" className="secondary-button compact-action-button" onClick={() => setReportPreviewOpen(true)}>
                  Preview PDF
                </button>
                <button type="button" className="primary-button compact-action-button" onClick={handleDownloadReportPdf}>
                  Download PDF
                </button>
              </div>
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
                  <strong>{finalReportPublishMode}</strong>
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
                    <p className="muted-copy">Choose a target language, then click Translate to generate the converted answer and speech-ready text with the selected tone.</p>
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
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void handleTranslate()}
                      disabled={!finalReport?.published_report || translationLoading}
                    >
                      {translationLoading ? 'Translating...' : 'Translate'}
                    </button>
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
                  <div className="translation-control">
                    <label className="field-label" htmlFor="speech-voice-style">Voice style</label>
                    <select
                      id="speech-voice-style"
                      value={selectedVoiceStyle}
                      onChange={(event) => setSelectedVoiceStyle(event.target.value)}
                    >
                      {voiceStyleOptions.map((option) => (
                        <option key={option.code} value={option.code}>{option.label}</option>
                      ))}
                    </select>
                    <p className="control-helper">{selectedVoiceStyleMeta.helper}</p>
                    <p className="control-helper accent-helper">
                      Voice selection is best-effort because installed browser voices vary by device and OS.
                    </p>
                  </div>
                  <div className="translation-control">
                    <label className="field-label" htmlFor="speech-voice-choice">Installed voice</label>
                    <label className="field-label" htmlFor="speech-voice-search">Search voices</label>
                    <input
                      id="speech-voice-search"
                      type="search"
                      value={voiceSearchQuery}
                      onChange={(event) => setVoiceSearchQuery(event.target.value)}
                      placeholder="Search installed voices"
                    />
                    <p className="control-helper">Type part of a voice name, language code, or style to narrow the list.</p>
                    <select
                      id="speech-voice-choice"
                      value={selectedVoiceURI}
                      onChange={(event) => handleVoiceSelection(event.target.value)}
                      disabled={!filteredVoiceOptions.length}
                    >
                      <option value="">Auto-select the best available voice</option>
                      {groupedVoiceOptions.map((group) => (
                        <optgroup key={group.label} label={`${group.label} (${group.voices.length})`}>
                          {group.voices.map((voice) => (
                            <option key={voice.voiceURI || `${voice.name}-${voice.lang}`} value={voice.voiceURI}>
                              {voice.label}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                    <p className="control-helper">
                      {selectedVoiceOption
                        ? `Selected installed voice: ${selectedVoiceOption.name}`
                        : 'No installed voice override selected yet.'}
                    </p>
                    <p className="control-helper accent-helper">
                      If the browser has multiple voices, choose the exact one here for the most predictable playback.
                    </p>
                    {voiceSearchQuery ? (
                      <button
                        type="button"
                        className="ghost-button compact-action-button"
                        onClick={() => setVoiceSearchQuery('')}
                      >
                        Clear voice search
                      </button>
                    ) : null}
                  </div>
                </div>
                {translationError ? <p className="inline-note danger">{translationError}</p> : null}
                <div className="translated-copy-card">
                  <span className="micro-label">{selectedLanguageMeta.label} output | {selectedProsodyMeta.label} tone | {selectedVoiceStyleMeta.label} voice | {selectedVoiceOption ? selectedVoiceOption.name : 'auto voice'}</span>
                  <p className="published-copy">
                    {translationLoading
                      ? `Translating the answer into ${selectedLanguageMeta.label}...`
                      : reportSpeechText || 'Choose a language and click Translate to generate the preview and speech output.'}
                  </p>
                  <div className="selection-summary-row">
                    <span className="selection-pill">Language: {selectedLanguageMeta.label}</span>
                    <span className="selection-pill">Tone: {selectedProsodyMeta.label}</span>
                    <span className="selection-pill">Voice: {selectedVoiceStyleMeta.label}</span>
                    <span className="selection-pill">{selectedVoiceOption ? selectedVoiceOption.name : 'Auto voice'}</span>
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

          {error ? (
            <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Error">
              <section className="error-modal">
                <p className="error-modal-message">{error}</p>
                <button type="button" className="btn-primary" onClick={() => setError('')}>Dismiss</button>
              </section>
            </div>
          ) : null}
        </main>
      </div>

      {reportPreviewOpen && finalReport ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="report-preview-title">
          <section className="report-preview-modal">
            <div className="modal-header">
              <div>
                <p className="eyebrow">PDF preview</p>
                <h2 id="report-preview-title">{finalReport.title}</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setReportPreviewOpen(false)}
                aria-label="Close PDF preview"
                title="Close PDF preview"
              >
                X
              </button>
            </div>
            <div className="pdf-preview-sheet">
              <h3>{finalReport.title}</h3>
              <p className="pdf-preview-meta"><strong>Question:</strong> {snapshot.question || 'Not available'}</p>
              <p className="pdf-preview-meta"><strong>Confidence:</strong> {Math.round(finalReport.confidence * 100)}%</p>
              <p className="pdf-preview-meta"><strong>Publish mode:</strong> {finalReportPublishMode}</p>
              <h4>Executive Summary</h4>
              <p>{finalReport.summary}</p>
              <h4>Published Answer</h4>
              <p className="published-copy">{finalReport.published_report}</p>
              <h4>Key Findings</h4>
              <ul>
                {finalReport.key_findings.map((item) => (
                  <li key={`preview-${item}`}>{item}</li>
                ))}
              </ul>
              <h4>Sources</h4>
              <ul>
                {finalReport.sources.length ? finalReport.sources.map((source) => (
                  <li key={`preview-${source.title}-${source.url}`}>
                    {source.title}{source.url ? ` - ${source.url}` : ''}
                  </li>
                )) : <li>No sources listed.</li>}
              </ul>
            </div>
            <div className="modal-action-row">
              <button type="button" className="secondary-button compact-action-button" onClick={() => setReportPreviewOpen(false)}>
                Close
              </button>
              <button type="button" className="primary-button compact-action-button" onClick={handleDownloadReportPdf}>
                Download PDF
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}

export default App
