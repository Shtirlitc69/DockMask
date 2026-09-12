// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiClient, saveBlobInBrowser } from "./clients"

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("local API client", () => {
  it("sends the selected label style with the document", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ job_id: "test", status: "queued" })),
    )
    await new ApiClient().createJob({
      file: new File(["pdf"], "test.pdf"), entityTypes: ["email"], labelStyle: "none",
    })
    const form = fetchMock.mock.calls[0][1]?.body as FormData
    expect(form.get("label_style")).toBe("none")
    expect(form.getAll("entity_types")).toEqual(["email"])
  })

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

  it("attaches the browser download link before clicking and cleans it later", () => {
    vi.useFakeTimers()
    const createObjectURL = vi.fn(() => "blob:dockmask")
    const revokeObjectURL = vi.fn()
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL })
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined)

    saveBlobInBrowser(new Blob(["report"]), "отчёт.csv")

    const anchor = document.body.querySelector("a")
    expect(anchor?.download).toBe("отчёт.csv")
    expect(anchor?.href).toBe("blob:dockmask")
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1000)
    expect(document.body.querySelector("a")).toBeNull()
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:dockmask")
  })
})
