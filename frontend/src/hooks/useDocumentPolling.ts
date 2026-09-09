import { useEffect, useRef, useState } from 'react';

import { apiClient } from '../api/clients';
import { mapBackendStatusToUi, type MappedStatus } from '../api/statusMapper';

const POLL_INTERVAL_MS = 2000;

export function useDocumentPolling(jobId: string | null) {
  const [mappedStatus, setMappedStatus] = useState<MappedStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let timeoutId: number | undefined;

    const poll = async () => {
      try {
        const response = await apiClient.getJob(jobId, controller.signal);
        setMappedStatus(mapBackendStatusToUi(response.status, response.progress));
        if (!['done', 'failed', 'needs_clarification'].includes(response.status) && !controller.signal.aborted) {
          timeoutId = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === 'AbortError') return;
        setError(reason instanceof Error ? reason.message : 'connection_failed');
      }
    };

    void poll();
    return () => {
      controller.abort();
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [jobId]);

  return { mappedStatus, error, stopPolling: () => abortControllerRef.current?.abort() };
}
