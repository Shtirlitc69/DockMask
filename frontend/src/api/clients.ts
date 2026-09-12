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
  ModelsRequest,
  PreviewResponse,
  ArtifactKind,
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

export function saveBlobInBrowser(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = Object.assign(document.createElement("a"), {
    href: url,
    download: filename,
  })
  anchor.style.display = "none"
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    anchor.remove()
    URL.revokeObjectURL(url)
  }, 1000)
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
    form.append("label_style", request.labelStyle ?? "full")

    for (const entityType of request.entityTypes)
      form.append("entity_types", entityType)

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

  cancelJob(jobId: string, signal?: AbortSignal): Promise<JobStatusResponse> {
    return this.request(
      "POST",
      `/jobs/${encodeURIComponent(jobId)}/cancel`,
      JSON.stringify({}),
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
    request: ModelsRequest,
    signal?: AbortSignal,
  ): Promise<ModelsResponse> {
    return this.request(
      "POST",
      "/config/models",
      JSON.stringify(request),
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

  getPreview(jobId: string, signal?: AbortSignal): Promise<PreviewResponse> {
    return this.request(
      "GET",
      `/jobs/${encodeURIComponent(jobId)}/preview`,
      undefined,
      signal,
    )
  }

  async downloadArtifact(jobId: string, artifact: ArtifactKind): Promise<Blob> {
    const endpoint = {
      document: "document",
      json: "report.json",
      csv: "report.csv",
      xlsx: "report.xlsx",
    }[artifact]
    const response = await fetch(
      `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/${endpoint}`,
    )
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as {
        detail?: unknown
      } | null
      throw new ApiError(
        response.status,
        typeof payload?.detail === "string" ? payload.detail : "request_failed",
      )
    }
    return response.blob()
  }

  downloadUrl(jobId: string, artifact: "document" | "report.xlsx"): string {
    return `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/${artifact}`
  }
}

export const apiClient = new ApiClient()
