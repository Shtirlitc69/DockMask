export type JobStatus = 'queued' | 'processing' | 'needs_clarification' | 'done' | 'failed';

export type EntityType =
  | 'person_name'
  | 'organization'
  | 'address'
  | 'amount'
  | 'inn'
  | 'kpp'
  | 'ogrn'
  | 'phone'
  | 'email'
  | 'bank_account'
  | 'bik'
  | 'contract_number';

export interface CreateJobRequest {
  file: File;
  entityTypes: EntityType[];
  ocrEnabled?: false;
}

export interface JobCreateResponse {
  job_id: string;
  status: JobStatus;
  source_filename: string;
  document_format: 'docx' | 'pdf' | 'xlsx';
}

export interface ClarificationQuestion {
  question_id: string;
  question: string;
  related_entity_type: EntityType | null;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  questions: ClarificationQuestion[];
  total_replacements: number;
  error: string | null;
}

export interface Answer {
  question_id: string;
  answer: 'supplier' | 'buyer' | 'unknown';
}

export interface AnswerBatchResponse {
  accepted: boolean;
  job_id: string;
  answers_count: number;
}

export interface ConfigResponse {
  feature_flags: Record<string, boolean>;
  has_api_key: boolean;
}

export interface ConfigUpdateRequest {
  api_key?: string;
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  db: 'ok' | 'unavailable';
  worker: 'ok' | 'unavailable';
}
