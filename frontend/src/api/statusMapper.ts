import type { JobStatus } from "./dto"

export type UiProcessingState = "idle" | "processing" | "waiting_clarification" | "completed" | "error"

export interface MappedStatus {
  uiState: UiProcessingState

  progress: number

  label: string

  isError: boolean
}

export function mapBackendStatusToUi(
  status: JobStatus,
  progress: number,
): MappedStatus {
  switch (status) {
    case "queued":
      return {
        uiState: "processing",
        progress,
        label: "В очереди...",
        isError: false,
      }

    case "processing":
      return {
        uiState: "processing",
        progress,
        label: "Обработка документа...",
        isError: false,
      }

    case "needs_clarification":
      return {
        uiState: "waiting_clarification",
        progress,
        label: "Требуются уточнения",
        isError: false,
      }

    case "done":
      return {
        uiState: "completed",
        progress: 100,
        label: "Готово",
        isError: false,
      }

    case "failed":
      return {
        uiState: "error",
        progress,
        label: "Ошибка обработки",
        isError: true,
      }
  }
}
