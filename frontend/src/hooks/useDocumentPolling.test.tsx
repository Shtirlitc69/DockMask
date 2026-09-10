// @vitest-environment jsdom
import { act, renderHook, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { apiClient } from "../api/clients"
import type { JobStatusResponse } from "../api/dto"
import { useDocumentPolling } from "./useDocumentPolling"

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

it("ignores a response arriving after stop even if transport ignores abort", async () => {
  let resolve!: (value: JobStatusResponse) => void
  vi.spyOn(apiClient, "getJob").mockImplementation(() => new Promise(r => { resolve = r }))
  const { result } = renderHook(() => useDocumentPolling("job"))
  act(() => result.current.stopPolling())
  await act(async () => resolve({ job_id: "job", status: "done", progress: 100 } as JobStatusResponse))
  expect(result.current.job).toBeNull()
})

it("clears scheduled polls on stop", async () => {
  vi.useFakeTimers()
  const request = vi.spyOn(apiClient, "getJob").mockResolvedValue({
    job_id: "job", status: "processing", progress: 10,
  } as JobStatusResponse)
  const { result } = renderHook(() => useDocumentPolling("job"))
  await act(async () => {})
  expect(vi.getTimerCount()).toBe(1)
  act(() => result.current.stopPolling())
  expect(vi.getTimerCount()).toBe(0)
  await act(async () => vi.advanceTimersByTimeAsync(5000))
  expect(request).toHaveBeenCalledTimes(1)
})