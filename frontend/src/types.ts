export type AppStep = "upload" | "processing" | "clarifying" | "results"

export type Theme = "dark" | "light"

export interface DataTypeOption {
  id: string

  label: string

  description: string

  category: "personal" | "financial" | "organization"

  markerPrefix: string

  selected: boolean

  color: string
}

export interface UploadedFile {
  name: string

  size: number

  mimeType: string

  isScanned: boolean

  pageCount: number
}

export interface DocSegment {
  text: string

  replacementId?: string
}

export interface DocLine {
  id: string

  type: "title" | "subtitle" | "label" | "field" | "text" | "divider" | "spacer"

  segments: DocSegment[]

  bold?: boolean

  centered?: boolean

  indent?: number
}

export interface DocTableCell {
  segments: DocSegment[]

  header?: boolean

  align?: "left" | "center" | "right"
}

export interface DocTable {
  id: string

  type: "table"

  rows: DocTableCell[][]
}

export type DocElement = DocLine | DocTable

export interface Replacement {
  id: string

  original: string

  masked: string

  typeId: string

  typeLabel: string

  confidence: number

  location: string
}

export interface ClarifyingQuestion {
  id: string

  question: string

  context: string

  reason?: string

  contexts?: Array<{ text: string; location: string; highlight_start: number; highlight_end: number }>

  contextLocation?: string

  highlightStart?: number

  highlightEnd?: number

  options: string[]

  answer?: string
}

export interface ProcessingStepDef {
  id: string

  label: string

  detail: string

  status: "pending" | "active" | "done" | "error"

  durationMs: number
}
