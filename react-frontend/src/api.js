import Ajv from 'ajv'
import {
  createSessionResponseSchema,
  resumeResearchRequestSchema,
  runSnapshotResponseSchema,
  startResearchRequestSchema,
  translateTextRequestSchema,
  translateTextResponseSchema,
} from './schemas'

const ajv = new Ajv({ allErrors: true, strict: true })
const validateCreateSessionResponse = ajv.compile(createSessionResponseSchema)
const validateStartRequest = ajv.compile(startResearchRequestSchema)
const validateResumeRequest = ajv.compile(resumeResearchRequestSchema)
const validateRunSnapshotResponse = ajv.compile(runSnapshotResponseSchema)
const validateTranslateRequest = ajv.compile(translateTextRequestSchema)
const validateTranslateResponse = ajv.compile(translateTextResponseSchema)

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'

function readErrors(validateFn) {
  return (validateFn.errors ?? []).map((item) => `${item.instancePath || '/'} ${item.message}`).join('; ')
}

function readFriendlyQuestionError(detail) {
  if (!Array.isArray(detail)) {
    return null
  }

  const questionIssue = detail.find((item) => Array.isArray(item?.loc) && item.loc.includes('question'))
  if (!questionIssue) {
    return null
  }

  const message = String(questionIssue.msg || '')
  if (message.includes('at least 8 characters')) {
    return 'Question is too short. Please enter at least 8 characters.'
  }
  if (message.includes('under 600 characters') || message.includes('at most 600 characters')) {
    return 'Question is too long. Please keep it under 600 characters.'
  }

  return message || 'Question is invalid.'
}

async function request(path, { method = 'GET', body, validateRequest, validateResponse } = {}) {
  if (validateRequest && body && !validateRequest(body)) {
    const questionIssue = (validateRequest.errors ?? []).find((item) => item.instancePath === '/question')
    if (questionIssue?.keyword === 'minLength') {
      throw new Error('Question is too short. Please enter at least 8 characters.')
    }
    if (questionIssue?.keyword === 'maxLength') {
      throw new Error('Question is too long. Please keep it under 600 characters.')
    }
    throw new Error(`Request schema validation failed: ${readErrors(validateRequest)}`)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  let data = null
  try {
    data = await response.json()
  } catch {
    data = null
  }

  if (!response.ok) {
    const detail = typeof data?.detail === 'string'
      ? data.detail
      : readFriendlyQuestionError(data?.detail) ?? (data ? JSON.stringify(data) : '')
    const error = new Error(detail || 'Request failed')
    error.status = response.status
    error.payload = data
    throw error
  }

  if (validateResponse && !validateResponse(data)) {
    throw new Error(`Response schema validation failed: ${readErrors(validateResponse)}`)
  }

  return data
}

export function createSession() {
  return request('/sessions', {
    method: 'POST',
    validateResponse: validateCreateSessionResponse,
  })
}

export function getSnapshot(threadId) {
  return request(`/runs/${threadId}`, {
    validateResponse: validateRunSnapshotResponse,
  })
}

export function startRun(payload) {
  return request('/runs/start', {
    method: 'POST',
    body: payload,
    validateRequest: validateStartRequest,
    validateResponse: validateRunSnapshotResponse,
  })
}

export function resumeRun(payload) {
  return request('/runs/resume', {
    method: 'POST',
    body: payload,
    validateRequest: validateResumeRequest,
    validateResponse: validateRunSnapshotResponse,
  })
}

export function translateText(payload) {
  return request('/translate', {
    method: 'POST',
    body: payload,
    validateRequest: validateTranslateRequest,
    validateResponse: validateTranslateResponse,
  })
}
