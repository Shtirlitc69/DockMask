/// <reference types="vite/client" />

import type { NativeSaveResult } from "./api/dto"

declare global {
  interface Window {
    pywebview?: {
      api?: {
        save_artifact?: (
          jobId: string,
          kind: string,
          suggestedFilename: string,
        ) => Promise<NativeSaveResult>
      }
    }
  }
}

export {}
