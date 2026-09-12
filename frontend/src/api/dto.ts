export type JobStatus = "queued" | "processing" | "needs_clarification" | "cancelled" | "done" | "failed"

export type EntityType = "person_name" | "organization" | "address" | "amount" | "inn" | "kpp" | "ogrn" | "phone" | "email" | "bank_account" | "bik" | "contract_number"

export type LabelStyle = "full" | "short" | "none"

export interface CreateJobRequest {
  labelStyle?: LabelStyle
  file: File

  entityTypes: EntityType[]

}

export interface JobCreateResponse {
  job_id: string

  status: JobStatus

  source_filename: string

  document_format: "docx" | "pdf" | "xlsx"
}

export interface ClarificationQuestion {
  question_id: string

  question: string

  related_entity_type: EntityType | null
  options: Array<"supplier" | "buyer" | "unknown">
  context_text?: string | null
  context_location?: string | null
  highlight_start?: number | null
  highlight_end?: number | null
}

export interface JobStatusResponse {
  job_id: string

  status: JobStatus

  progress: number

  questions: ClarificationQuestion[]

  total_replacements: number

  error: string | null
}

export interface Answer {
  question_id: string

  answer: "supplier" | "buyer" | "unknown"
}

export interface AnswerBatchResponse {
  accepted: boolean

  job_id: string

  answers_count: number
}

export interface ConfigResponse {
  feature_flags: Record<string, boolean>
  has_api_key: boolean
  provider: ProviderId
  model: string
  base_url: string | null
  scope: GigaChatScope | null
  providers: ProviderInfo[]
  certificate: CertificateInfo | null
}

export interface ConfigUpdateRequest {
  api_key?: string
  provider?: ProviderId
  model?: string
  base_url?: string | null
  scope?: GigaChatScope | null
  clear_api_key?: boolean
}

export type ProviderId = "mock" | "gigachat" | "openai" | "anthropic" | "openai_compatible" | "ollama" | "vllm"
export type GigaChatScope = "GIGACHAT_API_PERS" | "GIGACHAT_API_B2B" | "GIGACHAT_API_CORP"

export interface ProviderInfo {
  id: ProviderId
  display_name: string
  available: boolean
  requires_base_url: boolean
  api_key_optional: boolean
  development_only: boolean
  recommended_models: string[]
}

export interface CertificateInfo {
  state: "ready" | "expiring" | "expired" | "missing" | "integrity_failed"
  expires_at: string | null
}

export interface ConfigValidationRequest {
  provider: ProviderId
  model: string
  base_url?: string | null
  scope?: GigaChatScope | null
  api_key?: string
}

export interface ModelsRequest {
  provider: ProviderId
  base_url?: string | null
  scope?: GigaChatScope | null
  api_key?: string
}

export interface ConfigValidationResponse {
  ok: boolean
  code: string
  message: string
  certificate: CertificateInfo | null
}

export interface ModelInfo {
  id: string
  display_name: string
  capabilities: string[]
}

export interface ModelsResponse {
  models: ModelInfo[]
}

export interface ReplacementResponse {
  entity_type: EntityType
  original_value: string
  replacement: string
  location: Record<string, unknown>
  source: string
  confidence: number
  party_role: "supplier" | "buyer" | "unknown"
  applied: boolean
}

export interface ReportResponse {
  total_replacements: number
  replacements: ReplacementResponse[]
}

export interface PreviewSegment {
  text: string
  replacement: string | null
}

export interface PreviewLine {
  id: string
  type: "title" | "subtitle" | "label" | "field" | "text" | "divider" | "spacer"
  segments: PreviewSegment[]
}

export interface PreviewTableCell {
  segments: PreviewSegment[]
}

export interface PreviewTable {
  id: string
  type: "table"
  rows: PreviewTableCell[][]
}

export interface PreviewResponse {
  format: "docx" | "pdf" | "xlsx"
  elements: Array<PreviewLine | PreviewTable>
  truncated: boolean
}

export type ArtifactKind = "document" | "json" | "csv" | "xlsx"

export interface NativeSaveResult {
  status: "saved" | "cancelled" | "error"
  code?: string
  filename?: string
}

export interface HealthResponse {
  status: "ok" | "degraded"

  db: "ok" | "unavailable"

  worker: "ok" | "unavailable"
}
