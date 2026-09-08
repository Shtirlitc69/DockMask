// --- Запросы (Request) ---
export interface UploadDocumentRequest {
  file: File;
  settings?: {
    maskFio?: boolean;
    maskPassport?: boolean;
    // ... другие настройки из SettingsPage
  };
}

export interface AnswerQuestionRequest {
  questionId: string;
  answer: string; // или boolean, в зависимости от бэкенда
}

// --- Ответы (Response) ---
export interface UploadDocumentResponse {
  documentId: string;
  status: BackendDocumentStatus;
}

export interface DocumentStatusResponse {
  documentId: string;
  status: BackendDocumentStatus;
  progress: number; // 0-100
  currentStep: string;
  error?: string;
}

export interface ClarificationQuestionDto {
  id: string;
  question: string;
  context: string;
  options: string[];
}

export interface DocumentResultResponse {
  documentId: string;
  // Здесь будут типы вашего MOCK_DOCUMENT и MOCK_REPLACEMENTS
  // Импортируйте их или продублируйте структуру здесь
  content: any; 
  replacements: any[];
}

// --- Статусы бэкенда (Machine Statuses) ---
export type BackendDocumentStatus = 
  | 'PENDING' 
  | 'EXTRACTING' 
  | 'OCR_PROCESSING' 
  | 'LLM_ANALYZING' 
  | 'CLARIFICATION_NEEDED' 
  | 'COMPLETED' 
  | 'FAILED';