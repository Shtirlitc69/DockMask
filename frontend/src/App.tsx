import { apiClient } from './api/clients';
import { useState, useCallback, useRef, useEffect } from 'react';
import { StepBreadcrumb } from './components/StepBreadcrumb';
import { UploadPage } from './pages/UploadPage';
import { ProcessingPage } from './pages/ProcessingPage';
import { ClarificationPage } from './pages/ClarificationPage';
import { ResultsPage } from './pages/ResultsPage';
import { SettingsPage } from './pages/SettingsPage';
import { MOCK_DOCUMENT, MOCK_REPLACEMENTS, MOCK_QUESTIONS, DEFAULT_DATA_TYPES } from './mocks/mockData';
import type {
  AppStep,
  Theme,
  AIConfig,
  DataTypeOption,
  UploadedFile,
  Replacement,
  ClarifyingQuestion,
} from './types';

export default function App() {
  // --- Состояния ---
  const [theme, setTheme] = useState<Theme>('dark');
  const [step, setStep] = useState<AppStep>('upload');
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [dataTypes, setDataTypes] = useState<DataTypeOption[]>(DEFAULT_DATA_TYPES);
  const [replacements, setReplacements] = useState<Replacement[]>([]);
  const [questions, setQuestions] = useState<ClarifyingQuestion[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [aiConfig, setAIConfig] = useState<AIConfig>({
    provider: 'gigachat',
    baseUrl: 'https://gigachat.devices.sberbank.ru',
    apiKey: '',
    model: 'GigaChat-Pro',
    temperature: 0.1,
    maxTokens: 4096,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- Эффекты ---
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // --- Обработчики загрузки ---
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) {
      setFile({
        name: f.name,
        size: f.size,
        mimeType: f.type,
        isScanned: f.name.toLowerCase().endsWith('.pdf'),
        pageCount: Math.floor(Math.random() * 7) + 1,
        rawFile: f,
      });
    }
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile({
        name: f.name,
        size: f.size,
        mimeType: f.type,
        isScanned: f.name.toLowerCase().endsWith('.pdf'),
        pageCount: Math.floor(Math.random() * 7) + 1,
        rawFile: f,
      });
    }
  }, []);

  // --- Обработчики типов данных ---
  const handleToggleType = useCallback((id: string) => {
    setDataTypes(prev => prev.map(d => d.id === id ? { ...d, selected: !d.selected } : d));
  }, []);

  const handleProcess = useCallback(async () => {
    if (!file) return;

    try {
      // Реальный API-вызов
      const response = await apiClient.uploadDocument({ 
        file: file.rawFile,
        settings: {
          // Передаём выбранные типы данных
          maskFio: dataTypes.find(d => d.id === 'fio')?.selected,
          maskPassport: dataTypes.find(d => d.id === 'passport')?.selected,
        }
      });
    
    setDocumentId(response.documentId);
    setStep('processing');
  } catch (error: any) {
    console.error('Upload failed:', error);
    // Можно добавить toast-уведомление об ошибке
    alert(`Ошибка загрузки: ${error.message}`);
  }
}, [file, dataTypes]);

  // --- Переходы между шагами ---
  const handleProcessingDone = useCallback(async () => {
  if (!documentId) return;
  
  try {
      // Загружаем вопросы от AI
      const questionsResponse = await apiClient.getQuestions(documentId);
      setQuestions(questionsResponse.questions.map(q => ({ ...q })));

      // Загружаем результаты (замены)
      const resultsResponse = await apiClient.getResults(documentId);
      setReplacements(resultsResponse.replacements);

      setStep('clarification');
    } catch (error: any) {
      console.error('Failed to load questions/results:', error);

      // Fallback на моки, если бэкенд недоступен
      setReplacements(MOCK_REPLACEMENTS);
      setQuestions(MOCK_QUESTIONS.map(q => ({ ...q })));
      setStep('clarification');
    }
  }, [documentId]);
    
  const handleAnswer = useCallback(async (qId: string, answer: string) => {
    if (!documentId) return;
    
    try {
      await apiClient.answerQuestion(documentId, { questionId: qId, answer });
      setQuestions(prev => prev.map(q => q.id === qId ? { ...q, answer } : q));
    } catch (error: any) {
      console.error('Failed to answer question:', error);
      // Fallback: обновляем локально
      setQuestions(prev => prev.map(q => q.id === qId ? { ...q, answer } : q));
    }
  }, [documentId]);

  const handleFinalizeClarifying = useCallback(() => {
    setStep('results');
  }, []);

  // --- Экспорт отчётов ---
  const handleDownload = useCallback((fmt: 'json' | 'csv') => {
    if (fmt === 'json') {
      const blob = new Blob([JSON.stringify(replacements, null, 2)], { type: 'application/json' });
      const a = Object.assign(document.createElement('a'), {
        href: URL.createObjectURL(blob),
        download: 'anonymization_report.json',
      });
      a.click();
    } else {
      const rows = [
        '№,Тип данных,Исходный текст,Маркер,Уверенность,Расположение',
        ...replacements.map((r, i) =>
          `${i + 1},"${r.typeLabel}","${r.original}","${r.masked}","${Math.round(r.confidence * 100)}%","${r.location}"`
        ),
      ].join('\n');
      const blob = new Blob(['\ufeff' + rows], { type: 'text/csv;charset=utf-8' });
      const a = Object.assign(document.createElement('a'), {
        href: URL.createObjectURL(blob),
        download: 'anonymization_report.csv',
      });
      a.click();
    }
  }, [replacements]);

  // --- Сброс ---
  const handleReset = useCallback(() => {
    setFile(null);
    setDocumentId(null);
    setStep('upload');
    setReplacements([]);
    setQuestions([]);
  }, []);

  // --- Рендер ---
  return (
    <div
      className="min-h-full flex flex-col"
      style={{ background: 'var(--background)', color: 'var(--foreground)' }}
    >
      {/* Header — общий для всех шагов */}
      <header
        className="flex items-center gap-4 px-5 py-3 border-b shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}
      >
        <div className="flex items-center gap-2.5 mr-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
          >
            🔒
          </div>
          <span className="font-semibold text-base tracking-tight">DocMask</span>
        </div>

        <StepBreadcrumb step={step} />

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            className="w-9 h-9 flex items-center justify-center rounded-lg border transition-colors hover:bg-white/10"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
            title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button
            onClick={() => setSettingsOpen(true)}
            className="w-9 h-9 flex items-center justify-center rounded-lg border transition-colors hover:bg-white/10"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
            title="Настройки AI-агента"
          >
            ⚙️
          </button>
        </div>
      </header>

      {/* Main — переключаем страницы по шагу */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {step === 'upload' && (
          <UploadPage
            file={file}
            dataTypes={dataTypes}
            isDragging={isDragging}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onFileClick={() => fileInputRef.current?.click()}
            onFileInput={handleFileInput}
            fileInputRef={fileInputRef}
            onToggleType={handleToggleType}
            onProcess={handleProcess}
          />
        )}

        {step === 'processing' && documentId && (
          <ProcessingPage
            documentId={documentId}
            file={file}
            onDone={handleProcessingDone}
          />
        )}

        {step === 'clarification' && (
          <ClarificationPage
            questions={questions}
            onAnswer={handleAnswer}
            onConfirm={handleFinalizeClarifying}
          />
        )}

        {step === 'results' && (
          <ResultsPage
            replacements={replacements}
            questions={questions}
            document={MOCK_DOCUMENT}
            onDownload={handleDownload}
            onReset={handleReset}
          />
        )}
      </main>

      {settingsOpen && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setSettingsOpen(false)} />
          <div className="absolute right-0 top-0 h-full w-96">
            <SettingsPage
              config={aiConfig}
              onChange={setAIConfig}
              onClose={() => setSettingsOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}