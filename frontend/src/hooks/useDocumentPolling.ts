// frontend/src/hooks/useDocumentPolling.ts
import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../api/clients';
import { DocumentStatusResponse } from '../api/dto';
import { mapBackendStatusToUi, MappedStatus } from '../api/statusMapper';

const POLL_INTERVAL_MS = 2000; // Опрос каждые 2 секунды

export function useDocumentPolling(documentId: string | null) {
  const [mappedStatus, setMappedStatus] = useState<MappedStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // useRef для хранения AbortController, чтобы иметь возможность отменить polling извне
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!documentId) return;

    // Создаем новый контроллер для этой сессии polling
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    let timeoutId: number;

    const poll = async () => {
      try {
        // Запрашиваем статус, передавая signal
        const response: DocumentStatusResponse = await apiClient.getDocumentStatus(documentId, signal);
        
        // Маппим статус бэкенда в статус UI
        const uiStatus = mapBackendStatusToUi(response.status, response.progress);
        setMappedStatus(uiStatus);

        // Если статус финальный, останавливаем polling
        if (response.status === 'COMPLETED' || response.status === 'FAILED' || response.status === 'CLARIFICATION_NEEDED') {
          return; 
        }

        // Если не финальный, планируем следующий опрос
        if (!signal.aborted) {
          timeoutId = window.setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (err: any) {
        if (err.name === 'AbortError') return; // Игнорируем ошибки отмены
        setError(err.message || 'Ошибка опроса статуса');
      }
    };

    // Запускаем первый опрос сразу
    poll();

    // Функция очистки: срабатывает когда компонент размонтируется или меняется documentId
    return () => {
      abortControllerRef.current?.abort(); // Отменяем все активные запросы
      clearTimeout(timeoutId);
    };
  }, [documentId]);

  // Функция для принудительной остановки polling (например, по кнопке "Отмена")
  const stopPolling = () => {
    abortControllerRef.current?.abort();
  };

  return { mappedStatus, error, stopPolling };
}