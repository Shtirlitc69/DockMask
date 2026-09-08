export type AppStep = 'upload' | 'processing' | 'clarification' | 'results';
export type Theme = 'dark' | 'light';
export type AIProviderType = 'gigachat' | 'openai' | 'llama' | 'custom';

export interface DataTypeOption {
  id: string;
  label: string;
  description: string;
  category: 'personal' | 'financial' | 'organization';
  markerPrefix: string;
  selected: boolean;
  color: string;
}

export interface UploadedFile {
  name: string;
  size: number;
  mimeType: string;
  isScanned: boolean;
  pageCount: number;
  rawFile: File;
}

export interface DocSegment {
  text: string;
  replacementId?: string;
}

export interface DocLine {
  id: string;
  type: 'title' | 'subtitle' | 'label' | 'field' | 'text' | 'divider' | 'spacer';
  segments: DocSegment[];
  bold?: boolean;
  centered?: boolean;
  indent?: number;
}

export interface DocTableCell {
  segments: DocSegment[];
  header?: boolean;
  align?: 'left' | 'center' | 'right';
}

export interface DocTable {
  id: string;
  type: 'table';
  rows: DocTableCell[][];
}

export type DocElement = DocLine | DocTable;

export interface Replacement {
  id: string;
  original: string;
  masked: string;
  typeId: string;
  typeLabel: string;
  confidence: number;
  location: string;
}

export interface ClarifyingQuestion {
  id: string;
  question: string;
  context: string;
  options: string[];
  answer?: string;
}

export interface AIConfig {
  provider: AIProviderType;
  baseUrl: string;
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface TokenEntry {
  id: string;
  label: string;
  provider: AIProviderType;
  maskedToken: string;
  fullToken: string;
  isActive: boolean;
  createdAt: string;
}

export interface ProcessingStepDef {
  id: string;
  label: string;
  detail: string;
  status: 'pending' | 'active' | 'done' | 'error';
  durationMs: number;
}
