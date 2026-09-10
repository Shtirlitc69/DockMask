// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ClarifyingModal, LocalProviderNotice, SettingsDrawer } from "./App"

afterEach(() => {
  vi.restoreAllMocks()
})

describe("local provider notice", () => {
  it("explains privacy and accuracy tradeoffs", () => {
    render(<LocalProviderNotice />)

    expect(screen.getByText(/не отправляются внешним сервисам/)).toBeTruthy()
    expect(screen.getByText(/точность может быть ниже, чем у LLM/)).toBeTruthy()
  })
})

describe("clarification context", () => {
  it("shows the source location and highlights the matched party", () => {
    render(
      <ClarifyingModal
        questions={[
          {
            id: "party-1",
            question: "Определите роль стороны «ООО Альфа».",
            context: "Поставщик: ООО Альфа",
            contextLocation: "Страница 3",
            highlightStart: 11,
            highlightEnd: 20,
            options: ["supplier", "buyer", "unknown"],
          },
        ]}
        onAnswer={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        cancelling={false}
      />,
    )

    expect(screen.getByText("Страница 3")).toBeTruthy()
    expect(screen.getByText("ООО Альфа").tagName).toBe("MARK")
    expect(screen.getByText(/Система обнаружила/)).toBeTruthy()
  })
})

describe("model selection", () => {
  it("loads models after validation and replaces the current value on selection", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input)
      const payload = url.endsWith("/config/models")
        ? {
            models: [
              { id: "GigaChat-2-Max", display_name: "GigaChat-2-Max", capabilities: [] },
              { id: "GigaChat-3-Ultra", display_name: "GigaChat-3-Ultra", capabilities: [] },
            ],
          }
        : url.endsWith("/config/validate")
          ? { ok: true, code: "ok", message: "ok", certificate: null }
          : {
              feature_flags: {},
              has_api_key: false,
              provider: "gigachat",
              model: "GigaChat-2-Max",
              base_url: null,
              scope: "GIGACHAT_API_PERS",
              providers: [
                {
                  id: "gigachat",
                  display_name: "GigaChat",
                  available: true,
                  requires_base_url: false,
                  api_key_optional: false,
                  development_only: false,
                  recommended_models: [],
                },
              ],
              certificate: null,
            }
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    })

    render(<SettingsDrawer open onClose={vi.fn()} />)

    const modelInput = await screen.findByDisplayValue("GigaChat-2-Max")
    fireEvent.change(screen.getByLabelText("Ключ авторизации"), {
      target: { value: "secret" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Проверить" }))
    await screen.findByText("Подключение проверено. Список моделей загружен.")

    fireEvent.click(
      screen.getByRole("button", { name: "Открыть список моделей" }),
    )
    expect(screen.getByRole("option", { name: "GigaChat-3-Ultra" })).toBeTruthy()
    fireEvent.click(screen.getByRole("option", { name: "GigaChat-3-Ultra" }))

    expect((modelInput as HTMLInputElement).value).toBe("GigaChat-3-Ultra")
  })
})
