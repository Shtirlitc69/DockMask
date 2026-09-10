// @vitest-environment jsdom

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { LocalProviderNotice } from "./App"

describe("local provider notice", () => {
  it("explains privacy and accuracy tradeoffs", () => {
    render(<LocalProviderNotice />)

    expect(screen.getByText(/не отправляются внешним сервисам/)).toBeTruthy()
    expect(screen.getByText(/точность может быть ниже, чем у LLM/)).toBeTruthy()
  })
})
