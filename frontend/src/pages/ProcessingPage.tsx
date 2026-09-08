import { useEffect, useMemo } from 'react';
import { useDocumentPolling } from '../hooks/useDocumentPolling';
import { INITIAL_PROCESSING_STEPS } from '../mocks/mockData';
import type { UploadedFile, ProcessingStepDef } from '../types';
import type { UiProcessingState } from '../api/statusMapper';

interface Props {
  documentId: string;
  file: UploadedFile | null;
  onDone: () => void;
}

// Выносим за пределы компонента — это константа, не нужно пересоздавать
const STATUS_TO_INDEX: Record<UiProcessingState, number> = {
  'idle': 0,
  'uploading': 0,
  'extracting': 1,
  'ocr': 2,
  'llm': 3,
  'waiting_clarification': INITIAL_PROCESSING_STEPS.length - 1,
  'completed': INITIAL_PROCESSING_STEPS.length - 1,
  'error': -1, // Специальное значение для ошибки
};

export function ProcessingPage({ documentId, file, onDone }: Props) {
  const { mappedStatus, error, stopPolling } = useDocumentPolling(documentId);

  // Обновляем статусы шагов на основе текущего состояния
  const steps = useMemo<ProcessingStepDef[]>(() => {
    if (!mappedStatus) {
      return INITIAL_PROCESSING_STEPS.map(s => ({ ...s, status: 'pending' }));
    }

    const currentIndex = STATUS_TO_INDEX[mappedStatus.uiState] ?? 0;
    const isClarification = mappedStatus.uiState === 'waiting_clarification';
    const isError = mappedStatus.uiState === 'error';

    return INITIAL_PROCESSING_STEPS.map((step, index) => {
      // Если ошибка — помечаем текущий шаг как error
      if (isError) {
        if (index === INITIAL_PROCESSING_STEPS.length - 1) {
          return { ...step, status: 'error' };
        }
        if (index < INITIAL_PROCESSING_STEPS.length - 1) {
          return { ...step, status: 'done' };
        }
      }

      // Если ожидание уточнения — все шаги завершены
      if (isClarification) {
        return { ...step, status: 'done' };
      }

      // Обычная логика: done / active / pending
      if (index < currentIndex) {
        return { ...step, status: 'done' };
      } else if (index === currentIndex) {
        return { ...step, status: 'active' };
      } else {
        return { ...step, status: 'pending' };
      }
    });
  }, [mappedStatus]);

  // Вычисляем переменные как в оригинальном ProcessingView
  const doneCount = steps.filter(s => s.status === 'done').length;
  const progress = mappedStatus?.progress ?? (doneCount / steps.length) * 100;
  const activeStep = steps.find(s => s.status === 'active');

  // Автоматический переход при завершении
  useEffect(() => {
    if (mappedStatus?.uiState === 'completed' || mappedStatus?.uiState === 'waiting_clarification') {
      onDone();
    }
  }, [mappedStatus, onDone]);

  // Обработка ошибок
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center">
          <div className="text-4xl mb-4">❌</div>
          <div className="text-red-500 font-semibold">{error}</div>
          <button
            onClick={stopPolling}
            className="mt-4 px-4 py-2 rounded border"
            style={{ borderColor: 'var(--border)', color: 'var(--foreground)' }}
          >
            Отмена
          </button>
        </div>
      </div>
    );
  }

  // Состояние загрузки
  if (!mappedStatus) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div>Инициализация...</div>
      </div>
    );
  }

  // Основной рендер - полная копия из оригинального ProcessingView
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="w-full max-w-md space-y-8">
        {/* File + progress */}
        <div className="text-center space-y-3">
          <div className="text-4xl">
            {file?.name.endsWith('.pdf') ? '📄' : file?.name.endsWith('.docx') ? '📝' : '📊'}
          </div>
          <div className="font-semibold text-base" style={{ color: 'var(--foreground)' }}>
            {file?.name ?? 'документ'}
          </div>
          <div className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
            {activeStep?.label ?? (doneCount === steps.length ? 'Завершено' : 'Подготовка...')}
          </div>
          {/* Progress bar */}
          <div className="h-1 w-full rounded-full overflow-hidden" style={{ background: 'var(--secondary)' }}>
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${progress}%`, background: 'var(--primary)' }}
            />
          </div>
          <div className="mono text-xs" style={{ color: 'var(--muted-foreground)' }}>
            {doneCount} / {steps.length} шагов
          </div>
        </div>

        {/* Step list */}
        <div className="space-y-2">
          {steps.map(step => {
            const isDone = step.status === 'done';
            const isActive = step.status === 'active';
            const isPending = step.status === 'pending';
            const isError = step.status === 'error';
            return (
              <div
                key={step.id}
                className="flex items-center gap-3 px-4 py-3 rounded-lg transition-all"
                style={{
                  background: isActive
                    ? 'var(--secondary)'
                    : isError
                      ? 'rgba(239,68,68,.08)'
                      : 'transparent',
                  borderLeft: isActive
                    ? '2px solid var(--primary)'
                    : isError
                      ? '2px solid var(--danger)'
                      : '2px solid transparent',
                }}
              >
                {/* Status icon */}
                <div className="w-5 h-5 shrink-0 flex items-center justify-center">
                  {isDone && <span className="text-sm" style={{ color: 'var(--primary)' }}>✓</span>}
                  {isActive && (
                    <div
                      className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
                      style={{ borderColor: 'var(--primary)', borderTopColor: 'transparent' }}
                    />
                  )}
                  {isPending && <div className="w-2 h-2 rounded-full" style={{ background: 'var(--border)' }} />}
                  {isError && <span className="text-sm" style={{ color: 'var(--danger)' }}>✕</span>}
                </div>
                {/* Label */}
                <div className="flex-1 min-w-0">
                  <div
                    className="text-sm font-medium truncate"
                    style={{
                      color: isDone
                        ? 'var(--muted-foreground)'
                        : isActive
                          ? 'var(--foreground)'
                          : isError
                            ? 'var(--danger)'
                            : 'var(--muted-foreground)'
                    }}
                  >
                    {step.label}
                  </div>
                  {isActive && (
                    <div className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
                      {step.detail}
                    </div>
                  )}
                  {isError && (
                    <div className="text-xs mt-0.5" style={{ color: 'var(--danger)' }}>
                      Ошибка обработки
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}