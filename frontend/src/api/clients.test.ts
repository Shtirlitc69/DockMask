// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiClient } from "./clients"

afterEach(() => vi.restoreAllMocks())

describe("local API client", () => {
  it("sends a write-only key only to the local config endpoint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ feature_flags: {}, has_api_key: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    const storageSpy = vi.spyOn(Storage.prototype, "setItem")

    await new ApiClient().updateConfig({
      provider: "openai",
      model: "test-model",
      api_key: "secret",
    })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/config")
    expect(String(init?.body)).toContain("secret")
    expect(storageSpy).not.toHaveBeenCalled()
  })

  it("never constructs a direct provider URL", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ models: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )

    await new ApiClient().listModels({
      provider: "openai_compatible",
      base_url: "https://router.example/v1",
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe("/api/config/models")
    expect(String(url)).not.toMatch(/^https?:\/\//)
    expect(init?.method).toBe("POST")
    expect(String(init?.body)).toContain("router.example")
  })
})
