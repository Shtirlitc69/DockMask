import { describe, expect, it } from "vitest"

import { mapBackendStatusToUi } from "./statusMapper"

describe("job status mapping", () => {
  it("keeps all stable backend states", () => {
    expect(mapBackendStatusToUi("queued", 0).uiState).toBe("processing")
    expect(mapBackendStatusToUi("processing", 42).progress).toBe(42)
    expect(mapBackendStatusToUi("needs_clarification", 70).uiState).toBe(
      "waiting_clarification",
    )
    expect(mapBackendStatusToUi("done", 100).uiState).toBe("completed")
    expect(mapBackendStatusToUi("failed", 100).uiState).toBe("error")
  })
})
