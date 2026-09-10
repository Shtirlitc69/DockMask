import { useEffect, useRef, useState } from "react"

import { apiClient } from "../api/clients"
import type { JobStatusResponse } from "../api/dto"
import { mapBackendStatusToUi, type MappedStatus } from "../api/statusMapper"

const POLL_INTERVAL_MS = 2000

export function useDocumentPolling(jobId: string | null, revision = 0) {
  const [mappedStatus, setMappedStatus] = useState<MappedStatus | null>(null)
  const [job, setJob] = useState<JobStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const timeoutRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (!jobId) {
      setMappedStatus(null)
      setJob(null)
      setError(null)
      return
    }

    const controller = new AbortController()

    abortControllerRef.current = controller

    const poll = async () => {
      if (controller.signal.aborted) return
      try {
        const response = await apiClient.getJob(jobId, controller.signal)
        if (controller.signal.aborted) return
        setJob(response)
        setMappedStatus(
          mapBackendStatusToUi(response.status, response.progress),
        )

        if (
          !["done", "failed", "cancelled", "needs_clarification"].includes(
            response.status,
          ) &&
          !controller.signal.aborted
        ) {
          timeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (reason) {
        if (controller.signal.aborted) return
        if (reason instanceof DOMException && reason.name === "AbortError")
          return

        setError(reason instanceof Error ? reason.message : "connection_failed")
      }
    }

    void poll()

    return () => {
      controller.abort()

      clearTimeout(timeoutRef.current)
    }
  }, [jobId, revision])

  return {
    job,
    mappedStatus,
    error,
    stopPolling: () => {
      abortControllerRef.current?.abort()
      clearTimeout(timeoutRef.current)
    },
  }
}
