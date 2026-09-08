// frontend/src/api/statusMapper.ts
import { BackendDocumentStatus } from './dto';

export type UiProcessingState = 
  | 'idle' 
  | 'uploading' 
  | 'extracting' 
  | 'ocr' 
  | 'llm' 
  | 'waiting_clarification' 
  | 'completed' 
  | 'error';

export interface MappedStatus {
  uiState: UiProcessingState;
  progress: number;
  label: string;
  isError: boolean;
}

export function mapBackendStatusToUi(backendStatus: BackendDocumentStatus, progress: number): MappedStatus {
  switch (backendStatus) {
    case 'PENDING':
      return { uiState: 'uploading', progress: 5, label: 'Постановка в очередь...', isError: false };
    case 'EXTRACTING':
      return { uiState: 'extracting', progress: 20, label: 'Извлечение структуры...', isError: false };
    case 'OCR_PROCESSING':
      return { uiState: 'ocr', progress: 50, label: 'Распознавание текста (OCR)...', isError: false };
    case 'LLM_ANALYZING':
      return { uiState: 'llm', progress: 80, label: 'Анализ нейросетью (LLM)...', isError: false };
    case 'CLARIFICATION_NEEDED':
      return { uiState: 'waiting_clarification', progress: 100, label: 'Требуются уточнения', isError: false };
    case 'COMPLETED':
      return { uiState: 'completed', progress: 100, label: 'Готово', isError: false };
    case 'FAILED':
      return { uiState: 'error', progress, label: 'Ошибка обработки', isError: true };
    default:
      return { uiState: 'idle', progress: 0, label: 'Ожидание', isError: false };
  }
}