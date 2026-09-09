import type {
  Answer,
  AnswerBatchResponse,
  ConfigResponse,
  ConfigUpdateRequest,
  CreateJobRequest,
  HealthResponse,
  JobCreateResponse,
  JobStatusResponse,
  ConfigValidationRequest,
  ConfigValidationResponse,
  ModelsResponse,
  ProviderId,
  ReportResponse,
} from "./dto"

const BASE_URL = "/api"

const RETRY_DELAYS_MS = [250, 500] as const

export class ApiError extends Error {
  constructor(
    readonly status: number,

    readonly code: string,
  ) {
    super(code)
  }
}

async function sleep(milliseconds: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, milliseconds))
}

export class ApiClient {
  private async request<T,>(
    method: "GET" | "POST" | "PUT",

    endpoint: string,

    body?: BodyInit,

    signal?: AbortSignal,
  ): Promise<T> {
    for (let attempt = 0; ; attempt += 1) {
      try {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
          method,

          headers:
            body instanceof FormData
              ? undefined
              : { "Content-Type": "application/json" },

          body,

          signal,
        })

        if (response.ok) return (await response.json()) as T

        const payload = (await response.json().catch(() => null)) as {
          detail?: unknown
        } | null

        const code =
          typeof payload?.detail === "string"
            ? payload.detail
            : "request_failed"

        if (response.status < 500 || attempt === RETRY_DELAYS_MS.length) {
          throw new ApiError(response.status, code)
        }
      } catch (error) {
        if (
          error instanceof ApiError ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          throw error
        }

        if (attempt === RETRY_DELAYS_MS.length)
          throw new ApiError(0, "connection_failed")
      }

      await sleep(RETRY_DELAYS_MS[attempt])
    }
  }

  createJob(
    request: CreateJobRequest,
    signal?: AbortSignal,
  ): Promise<JobCreateResponse> {
    const form = new FormData()

    form.append("file", request.file)

    for (const entityType of request.entityTypes)
      form.append("entity_types", entityType)

    form.append("ocr_enabled", String(request.ocrEnabled ?? false))

    return this.request("POST", "/jobs", form, signal)
  }

  getJob(jobId: string, signal?: AbortSignal): Promise<JobStatusResponse> {
    return this.request(
      "GET",
      `/jobs/${encodeURIComponent(jobId)}`,
      undefined,
      signal,
    )
  }

  submitAnswers(
    jobId: string,
    answers: Answer[],
    signal?: AbortSignal,
  ): Promise<AnswerBatchResponse> {
    return this.request(
      "POST",
      `/jobs/${encodeURIComponent(jobId)}/answers`,
      JSON.stringify({ answers }),
      signal,
    )
  }

  getConfig(signal?: AbortSignal): Promise<ConfigResponse> {
    return this.request("GET", "/config", undefined, signal)
  }

  updateConfig(
    request: ConfigUpdateRequest,
    signal?: AbortSignal,
  ): Promise<ConfigResponse> {
    return this.request("PUT", "/config", JSON.stringify(request), signal)
  }

  getHealth(signal?: AbortSignal): Promise<HealthResponse> {
    return this.request("GET", "/health", undefined, signal)
  }

  validateConfig(
    request: ConfigValidationRequest,
    signal?: AbortSignal,
  ): Promise<ConfigValidationResponse> {
    return this.request(
      "POST",
      "/config/validate",
      JSON.stringify(request),
      signal,
    )
  }

  listModels(
    provider: ProviderId,
    baseUrl?: string | null,
    signal?: AbortSignal,
  ): Promise<ModelsResponse> {
    const query = new URLSearchParams({ provider })
    if (baseUrl) query.set("base_url", baseUrl)
    return this.request(
      "GET",
      `/config/models?${query.toString()}`,
      undefined,
      signal,
    )
  }

  getReport(jobId: string, signal?: AbortSignal): Promise<ReportResponse> {
    return this.request(
      "GET",
      `/jobs/${encodeURIComponent(jobId)}/report`,
      undefined,
      signal,
    )
  }

  downloadUrl(jobId: string, artifact: "document" | "report.xlsx"): string {
    return `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/${artifact}`
  }
}

export const apiClient = new ApiClient()
