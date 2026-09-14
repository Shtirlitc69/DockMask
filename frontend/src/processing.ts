import type { JobStatusResponse } from "./api/dto"
import { PROCESSING_STEPS } from "./options"
import type { ProcessingStepDef } from "./types"

export function processingStepsForJob(job: JobStatusResponse): ProcessingStepDef[] {
  return PROCESSING_STEPS.map((item) => {
    const stage = job.stages?.find((candidate) => candidate.id === item.id)
    return {
      ...item,
      status: stage?.status === "waiting" ? "active"
        : stage?.status === "cancelled" ? "error"
        : stage?.status ?? (job.status === "done" ? "done" : "pending"),
      detail: stage?.detail || item.detail,
      durationMs: stage?.started_at && stage?.finished_at
        ? Date.parse(stage.finished_at) - Date.parse(stage.started_at) : 0,
    }
  })
}
