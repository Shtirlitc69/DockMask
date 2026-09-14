import { expect, it } from "vitest"
import type { JobStatusResponse } from "./api/dto"
import { processingStepsForJob } from "./processing"

it("uses actual stages even if a legacy percentage contradicts them", () => {
  const steps = processingStepsForJob({ status: "processing", progress: 5, stages: [
    {id: "extract", status: "done", started_at: "2026-01-01T00:00:00Z", finished_at: "2026-01-01T00:00:01Z", detail: ""},
    {id: "detect", status: "active", detail: "Повтор запроса", started_at: null, finished_at: null},
  ]} as JobStatusResponse)
  expect(steps[0].status).toBe("done")
  expect(steps[0].durationMs).toBe(1000)
  expect(steps[1].status).toBe("active")
  expect(steps[1].detail).toBe("Повтор запроса")
  expect(steps[2].status).toBe("pending")
})

it("does not invent successful stages after failure or cancellation", () => {
  for (const status of ["failed", "cancelled"] as const) {
    expect(processingStepsForJob({status, progress: 100} as JobStatusResponse).every(s => s.status === "pending")).toBe(true)
  }
})

it("keeps clarification active while awaiting the user", () => {
  const steps = processingStepsForJob({status: "needs_clarification", stages: [
    {id: "clarify", status: "waiting", detail: "Ожидание ответов", started_at: null, finished_at: null},
  ]} as JobStatusResponse)
  expect(steps[2].status).toBe("active")
  expect(steps[3].status).toBe("pending")
})
