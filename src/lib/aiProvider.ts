import type { AIConfig, AIProviderType, DocElement, Replacement, ClarifyingQuestion } from '../types';

// ---------------------------------------------------------------------------
// Abstract interface — swap any provider without touching application logic
// ---------------------------------------------------------------------------

export interface AnalysisResult {
  replacements: Replacement[];
  questions: ClarifyingQuestion[];
}

export interface AIProvider {
  readonly name: string;
  readonly providerType: AIProviderType;
  analyzeDocument(elements: DocElement[], dataTypeIds: string[]): Promise<AnalysisResult>;
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function buildSystemPrompt(dataTypeIds: string[]): string {
  return [
    'Ты — специалист по обезличиванию документов на русском языке.',
    `Найди и замени следующие типы данных: ${dataTypeIds.join(', ')}.`,
    'Верни JSON: { "replacements": [{id, original, masked, typeId, location, confidence}], "questions": [{id, question, context, options}] }',
    'Используй маркеры вида [ТИП_ПОРЯДКОВЫЙ_НОМЕР], например [ФИО_1], [ИНН_2].',
    'Для неоднозначных случаев добавляй уточняющий вопрос в массив questions.',
  ].join('\n');
}

function parseAIResponse(content: string | undefined): AnalysisResult {
  if (!content) return { replacements: [], questions: [] };
  try {
    const json = JSON.parse(content.replace(/```json|```/g, '').trim());
    return {
      replacements: Array.isArray(json.replacements) ? json.replacements : [],
      questions: Array.isArray(json.questions) ? json.questions : [],
    };
  } catch {
    return { replacements: [], questions: [] };
  }
}

// ---------------------------------------------------------------------------
// GigaChat provider (Sber AI)
// ---------------------------------------------------------------------------

class GigaChatProvider implements AIProvider {
  readonly name = 'GigaChat';
  readonly providerType: AIProviderType = 'gigachat';

  constructor(private config: AIConfig) {}

  async analyzeDocument(elements: DocElement[], dataTypeIds: string[]): Promise<AnalysisResult> {
    const response = await fetch(`${this.config.baseUrl}/api/v1/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.apiKey}`,
        'Content-Type': 'application/json',
        'RqUID': crypto.randomUUID(),
      },
      body: JSON.stringify({
        model: this.config.model || 'GigaChat-Pro',
        messages: [
          { role: 'system', content: buildSystemPrompt(dataTypeIds) },
          { role: 'user', content: JSON.stringify(elements) },
        ],
        temperature: this.config.temperature,
        max_tokens: this.config.maxTokens,
      }),
    });
    const data = await response.json();
    return parseAIResponse(data?.choices?.[0]?.message?.content);
  }
}

// ---------------------------------------------------------------------------
// OpenAI-compatible provider
// ---------------------------------------------------------------------------

class OpenAIProvider implements AIProvider {
  readonly name = 'OpenAI';
  readonly providerType: AIProviderType = 'openai';

  constructor(private config: AIConfig) {}

  async analyzeDocument(elements: DocElement[], dataTypeIds: string[]): Promise<AnalysisResult> {
    const response = await fetch(`${this.config.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: this.config.model || 'gpt-4o',
        messages: [
          { role: 'system', content: buildSystemPrompt(dataTypeIds) },
          { role: 'user', content: JSON.stringify(elements) },
        ],
        temperature: this.config.temperature,
        max_tokens: this.config.maxTokens,
        response_format: { type: 'json_object' },
      }),
    });
    const data = await response.json();
    return parseAIResponse(data?.choices?.[0]?.message?.content);
  }
}

// ---------------------------------------------------------------------------
// LLaMA / Ollama local provider
// ---------------------------------------------------------------------------

class LlamaProvider implements AIProvider {
  readonly name = 'LLaMA (local)';
  readonly providerType: AIProviderType = 'llama';

  constructor(private config: AIConfig) {}

  async analyzeDocument(elements: DocElement[], dataTypeIds: string[]): Promise<AnalysisResult> {
    const response = await fetch(`${this.config.baseUrl}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.config.model || 'llama3.1:8b',
        messages: [
          { role: 'system', content: buildSystemPrompt(dataTypeIds) },
          { role: 'user', content: JSON.stringify(elements) },
        ],
        stream: false,
        format: 'json',
      }),
    });
    const data = await response.json();
    return parseAIResponse(data?.message?.content);
  }
}

// ---------------------------------------------------------------------------
// Custom / generic OpenAI-compatible endpoint
// ---------------------------------------------------------------------------

class CustomProvider implements AIProvider {
  readonly name = 'Custom';
  readonly providerType: AIProviderType = 'custom';

  constructor(private config: AIConfig) {}

  async analyzeDocument(elements: DocElement[], dataTypeIds: string[]): Promise<AnalysisResult> {
    const response = await fetch(`${this.config.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${this.config.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: this.config.model,
        messages: [
          { role: 'system', content: buildSystemPrompt(dataTypeIds) },
          { role: 'user', content: JSON.stringify(elements) },
        ],
        temperature: this.config.temperature,
        max_tokens: this.config.maxTokens,
      }),
    });
    const data = await response.json();
    return parseAIResponse(data?.choices?.[0]?.message?.content);
  }
}

// ---------------------------------------------------------------------------
// Factory — single point of provider creation
// ---------------------------------------------------------------------------

export function createAIProvider(config: AIConfig): AIProvider {
  switch (config.provider) {
    case 'gigachat': return new GigaChatProvider(config);
    case 'openai':   return new OpenAIProvider(config);
    case 'llama':    return new LlamaProvider(config);
    case 'custom':   return new CustomProvider(config);
    default:         return new GigaChatProvider(config);
  }
}

export const PROVIDER_META: Record<AIProviderType, { label: string; defaultUrl: string; defaultModel: string; requiresKey: boolean }> = {
  gigachat: { label: 'GigaChat (Sber)',        defaultUrl: 'https://gigachat.devices.sberbank.ru', defaultModel: 'GigaChat-Pro',  requiresKey: true  },
  openai:   { label: 'OpenAI / совместимый',   defaultUrl: 'https://api.openai.com',              defaultModel: 'gpt-4o',        requiresKey: true  },
  llama:    { label: 'LLaMA (локальный)',       defaultUrl: 'http://localhost:11434',              defaultModel: 'llama3.1:8b',   requiresKey: false },
  custom:   { label: 'Custom endpoint',         defaultUrl: 'http://localhost:8080',               defaultModel: 'my-model',      requiresKey: false },
};
