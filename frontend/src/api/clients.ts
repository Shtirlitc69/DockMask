// frontend/src/api/client.ts

const BASE_URL = '/api'; // Или ваш URL бэкенда
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

class ApiClient {
  // Базовый метод запроса с логикой Retries и AbortController
  private async request<T>(
    method: 'GET' | 'POST' | 'PUT' | 'DELETE',
    endpoint: string,
    data?: any,
    signal?: AbortSignal
  ): Promise<T> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
          method,
          headers: data instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
          body: data instanceof FormData ? data : data ? JSON.stringify(data) : undefined,
          signal, // Передаем AbortSignal для отмены запроса
        });

        if (!response.ok) {
          // Если ошибка 4xx (клиентская), не ретраим, сразу падаем
          if (response.status >= 400 && response.status < 500) {
            const errorData = await response.json().catch(() => ({}));
            throw new ApiError(errorData.message || 'Client Error', response.status);
          }
          // Если 5xx (серверная), пробуем ретрай
          throw new ApiError(`Server Error: ${response.status}`, response.status);
        }

        return await response.json();
      } catch (error: any) {
        // Если запрос был отменен вручную (AbortController), сразу выходим
        if (error.name === 'AbortError') {
          throw error;
        }

        lastError = error;

        // Если это последняя попытка, пробрасываем ошибку
        if (attempt === MAX_RETRIES) {
          break;
        }

        // Exponential backoff: ждем 1с, потом 2с, потом 4с перед следующим ретраем
        const delay = RETRY_DELAY_MS * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }

    throw lastError || new Error('Unknown API error');
  }

  // --- Публичные методы API ---

  async uploadDocument(data: UploadDocumentRequest, signal?: AbortSignal) {
    const formData = new FormData();
    formData.append('file', data.file);
    if (data.settings) formData.append('settings', JSON.stringify(data.settings));

    return this.request<UploadDocumentResponse>('POST', '/documents/upload', formData, signal);
  }

  async getDocumentStatus(documentId: string, signal?: AbortSignal) {
    return this.request<DocumentStatusResponse>('GET', `/documents/${documentId}/status`, undefined, signal);
  }

  async getQuestions(documentId: string, signal?: AbortSignal) {
    return this.request<{ questions: ClarificationQuestionDto[] }>('GET', `/documents/${documentId}/questions`, undefined, signal);
  }

  async answerQuestion(documentId: string, data: AnswerQuestionRequest, signal?: AbortSignal) {
    return this.request<void>('POST', `/documents/${documentId}/questions/answer`, data, signal);
  }

  async getResults(documentId: string, signal?: AbortSignal) {
    return this.request<DocumentResultResponse>('GET', `/documents/${documentId}/result`, undefined, signal);
  }
}

export const apiClient = new ApiClient();