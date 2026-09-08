import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import TokenManager from './components/TokenManager';
import { PROVIDER_META } from './lib/aiProvider';
import {
  MOCK_DOCUMENT,
  MOCK_REPLACEMENTS,
  MOCK_QUESTIONS,
  INITIAL_PROCESSING_STEPS,
  DEFAULT_DATA_TYPES,
} from './mockData';
import type {
  AppStep,
  Theme,
  AIConfig,
  AIProviderType,
  DataTypeOption,
  UploadedFile,
  Replacement,
  ClarifyingQuestion,
  ProcessingStepDef,
  DocElement,
  DocLine,
  DocTable,
  DocSegment,
  DocTableCell,
} from './types';

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function fmtBytes(b: number) {
  if (b < 1024) return `${b} Б`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} КБ`;
  return `${(b / 1048576).toFixed(1)} МБ`;
}

function confidenceColor(c: number) {
  if (c >= 0.98) return '#10b981';
  if (c >= 0.93) return '#f59e0b';
  return '#ef4444';
}

const CATEGORY_LABELS: Record<string, string> = {
  personal: 'Персональные данные',
  financial: 'Финансовые данные',
  organization: 'Данные организации',
};

// ---------------------------------------------------------------------------
// Replacement marker badge (shown inline in document preview)
// ---------------------------------------------------------------------------

function RepBadge({ rep }: { rep: Replacement }) {
  const [hov, setHov] = useState(false);
  return (
    <span
      className="relative inline-block cursor-help mx-0.5 align-baseline"
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      <span
        className="mono rounded px-1.5 py-0.5 text-[11px] font-semibold border"
        style={{ background: 'rgba(0,201,167,.13)', color: '#00c9a7', borderColor: 'rgba(0,201,167,.3)' }}
      >
        {rep.masked}
      </span>
      {hov && (
        <span
          className="absolute z-20 bottom-full left-0 mb-1.5 rounded border shadow-xl px-2.5 py-1.5 text-xs whitespace-nowrap pointer-events-none"
          style={{ background: 'var(--card)', borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
        >
          <span className="block text-[10px] uppercase tracking-wider mb-0.5" style={{ color: 'var(--muted-foreground)' }}>
            Исходный текст
          </span>
          <span style={{ color: 'var(--foreground)' }}>{rep.original}</span>
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Document preview — renders MOCK_DOCUMENT with inline replacement badges
// ---------------------------------------------------------------------------

function DocumentPreview({ document, replacements }: { document: DocElement[]; replacements: Replacement[] }) {
  const repMap = useMemo(() => {
    const m: Record<string, Replacement> = {};
    replacements.forEach(r => { m[r.id] = r; });
    return m;
  }, [replacements]);

  function renderSegments(segments: DocSegment[]) {
    return segments.map((seg, i) => {
      if (seg.replacementId && repMap[seg.replacementId]) {
        return <RepBadge key={i} rep={repMap[seg.replacementId]} />;
      }
      return <span key={i}>{seg.text}</span>;
    });
  }

  function renderCell(cell: DocTableCell, key: string | number) {
    const align = cell.align === 'right' ? 'text-right' : cell.align === 'center' ? 'text-center' : 'text-left';
    return (
      <td
        key={key}
        className={`py-1.5 px-2.5 text-[12px] border-b ${align}`}
        style={{
          borderColor: '#d1d5db',
          fontWeight: cell.header ? 600 : 400,
          background: cell.header ? '#f3f4f6' : 'transparent',
          color: '#111827',
        }}
      >
        {renderSegments(cell.segments)}
      </td>
    );
  }

  return (
    <div
      className="rounded-lg shadow-xl overflow-auto text-[13px] leading-relaxed"
      style={{ background: '#fff', color: '#111827', fontFamily: "'Outfit', sans-serif", minHeight: 400 }}
    >
      <div className="p-8 space-y-1.5">
        {document.map(elem => {
          // Table
          if (elem.type === 'table') {
            const tbl = elem as DocTable;
            return (
              <div key={tbl.id} className="overflow-x-auto my-3">
                <table className="w-full border-collapse border rounded text-xs" style={{ borderColor: '#d1d5db' }}>
                  <tbody>
                    {tbl.rows.map((row, ri) => (
                      <tr key={ri}>
                        {row.map((c, ci) => renderCell(c, ci))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          }

          const line = elem as DocLine;
          if (line.type === 'divider') {
            return <hr key={line.id} style={{ borderColor: '#e5e7eb', marginTop: 6, marginBottom: 6 }} />;
          }
          if (line.type === 'spacer') {
            return <div key={line.id} className="h-2" />;
          }

          const cn = [
            line.type === 'title' ? 'text-base font-bold tracking-wide' : '',
            line.type === 'subtitle' ? 'text-sm text-gray-500' : '',
            line.type === 'label' ? 'text-[11px] font-semibold tracking-widest uppercase mt-1 text-gray-500' : '',
            line.type === 'field' ? 'text-[13px]' : '',
            line.type === 'text' ? 'text-xs text-gray-400 italic' : '',
            line.bold ? 'font-semibold' : '',
            line.centered ? 'text-center' : '',
          ].filter(Boolean).join(' ');

          return (
            <div
              key={line.id}
              className={cn}
              style={line.indent ? { paddingLeft: `${line.indent * 16}px` } : {}}
            >
              {renderSegments(line.segments)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Replacement report table
// ---------------------------------------------------------------------------

function ReplacementReport({ replacements }: { replacements: Replacement[] }) {
  const [filter, setFilter] = useState('');
  const filtered = replacements.filter(r =>
    !filter || r.typeLabel.toLowerCase().includes(filter.toLowerCase()) ||
    r.original.toLowerCase().includes(filter.toLowerCase()) ||
    r.location.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Фильтр..."
          className="flex-1 text-sm px-3 py-1.5 rounded border outline-none"
          style={{ background: 'var(--secondary)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
        />
        <span className="text-xs px-2.5 py-1 rounded"
          style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>
          {filtered.length} / {replacements.length}
        </span>
      </div>

      <div className="overflow-x-auto rounded border" style={{ borderColor: 'var(--border)' }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: 'var(--secondary)' }}>
              {['#', 'Тип', 'Исходный текст', 'Маркер', 'Расположение', 'Уверен.'].map(h => (
                <th key={h} className="px-3 py-2 text-left font-semibold tracking-wide"
                  style={{ color: 'var(--muted-foreground)', borderBottom: '1px solid var(--border)' }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={r.id} className="transition-colors hover:bg-white/5"
                style={{ borderBottom: '1px solid var(--border)' }}>
                <td className="px-3 py-2 mono" style={{ color: 'var(--muted-foreground)' }}>{i + 1}</td>
                <td className="px-3 py-2">
                  <span className="px-2 py-0.5 rounded text-[11px] font-medium"
                    style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>
                    {r.typeLabel}
                  </span>
                </td>
                <td className="px-3 py-2 max-w-[200px] truncate" style={{ color: 'var(--foreground)' }}
                  title={r.original}>
                  {r.original}
                </td>
                <td className="px-3 py-2">
                  <span className="mono text-[11px] px-1.5 py-0.5 rounded border"
                    style={{ background: 'rgba(0,201,167,.1)', color: '#00c9a7', borderColor: 'rgba(0,201,167,.25)' }}>
                    {r.masked}
                  </span>
                </td>
                <td className="px-3 py-2" style={{ color: 'var(--muted-foreground)' }}>{r.location}</td>
                <td className="px-3 py-2">
                  <span className="mono font-semibold" style={{ color: confidenceColor(r.confidence) }}>
                    {Math.round(r.confidence * 100)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Settings panel (inside drawer)
// ---------------------------------------------------------------------------

function AISettingsPanel({ config, onChange }: { config: AIConfig; onChange: (c: AIConfig) => void }) {
  const meta = PROVIDER_META[config.provider];

  return (
    <div className="space-y-4">
      <div className="text-xs font-semibold tracking-widest uppercase mb-2"
        style={{ color: 'var(--muted-foreground)' }}>
        Настройки AI-агента
      </div>

      {/* Provider */}
      <div className="space-y-1.5">
        <label className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Провайдер</label>
        <select
          value={config.provider}
          onChange={e => {
            const p = e.target.value as AIProviderType;
            const m = PROVIDER_META[p];
            onChange({ ...config, provider: p, baseUrl: m.defaultUrl, model: m.defaultModel });
          }}
          className="w-full text-sm px-3 py-2 rounded border outline-none"
          style={{ background: 'var(--secondary)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
        >
          {(Object.entries(PROVIDER_META) as [AIProviderType, typeof PROVIDER_META[AIProviderType]][]).map(([id, m]) => (
            <option key={id} value={id}>{m.label}</option>
          ))}
        </select>
      </div>

      {/* Base URL */}
      <div className="space-y-1.5">
        <label className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Base URL</label>
        <input
          value={config.baseUrl}
          onChange={e => onChange({ ...config, baseUrl: e.target.value })}
          className="w-full mono text-xs px-3 py-2 rounded border outline-none"
          style={{ background: 'var(--secondary)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
        />
      </div>

      {/* API Key */}
      {meta.requiresKey && (
        <div className="space-y-1.5">
          <label className="text-xs" style={{ color: 'var(--muted-foreground)' }}>API-ключ</label>
          <input
            type="password"
            value={config.apiKey}
            onChange={e => onChange({ ...config, apiKey: e.target.value })}
            placeholder="sk-... или Bearer token"
            className="w-full mono text-xs px-3 py-2 rounded border outline-none"
            style={{ background: 'var(--secondary)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
          />
        </div>
      )}

      {/* Model */}
      <div className="space-y-1.5">
        <label className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Модель</label>
        <input
          value={config.model}
          onChange={e => onChange({ ...config, model: e.target.value })}
          className="w-full mono text-xs px-3 py-2 rounded border outline-none"
          style={{ background: 'var(--secondary)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
        />
      </div>

      {/* Temperature */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs">
          <span style={{ color: 'var(--muted-foreground)' }}>Температура</span>
          <span className="mono" style={{ color: 'var(--foreground)' }}>{config.temperature.toFixed(2)}</span>
        </div>
        <input
          type="range" min={0} max={1} step={0.05}
          value={config.temperature}
          onChange={e => onChange({ ...config, temperature: +e.target.value })}
          className="w-full accent-teal-400"
        />
      </div>

      {/* Max tokens */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs">
          <span style={{ color: 'var(--muted-foreground)' }}>Max tokens</span>
          <span className="mono" style={{ color: 'var(--foreground)' }}>{config.maxTokens}</span>
        </div>
        <input
          type="range" min={512} max={16384} step={256}
          value={config.maxTokens}
          onChange={e => onChange({ ...config, maxTokens: +e.target.value })}
          className="w-full accent-teal-400"
        />
      </div>

      {/* Divider */}
      <hr style={{ borderColor: 'var(--border)', marginTop: 12, marginBottom: 12 }} />

      {/* Token Manager */}
      <TokenManager />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Settings drawer
// ---------------------------------------------------------------------------

function SettingsDrawer({ open, onClose, config, onConfigChange }: {
  open: boolean;
  onClose: () => void;
  config: AIConfig;
  onConfigChange: (c: AIConfig) => void;
}) {
  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}
      {/* Panel */}
      <div
        className="fixed top-0 right-0 h-full z-40 w-80 flex flex-col overflow-y-auto transition-transform duration-300 ease-out"
        style={{
          background: 'var(--card)',
          borderLeft: '1px solid var(--border)',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
        }}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b"
          style={{ borderColor: 'var(--border)' }}>
          <span className="font-semibold text-sm">Настройки</span>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded transition-colors hover:bg-white/10"
            style={{ color: 'var(--muted-foreground)' }}>✕</button>
        </div>
        <div className="flex-1 p-5">
          <AISettingsPanel config={config} onChange={onConfigChange} />
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Clarifying questions modal
// ---------------------------------------------------------------------------

function ClarifyingModal({ questions, onAnswer, onConfirm }: {
  questions: ClarifyingQuestion[];
  onAnswer: (qId: string, answer: string) => void;
  onConfirm: () => void;
}) {
  const allAnswered = questions.every(q => q.answer);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl shadow-2xl border overflow-hidden"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
        {/* Header */}
        <div className="px-6 py-4 border-b flex items-start gap-3"
          style={{ borderColor: 'var(--border)' }}>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-lg shrink-0 mt-0.5"
            style={{ background: 'rgba(245,158,11,.15)', color: '#f59e0b' }}>
            ?
          </div>
          <div>
            <div className="font-semibold text-sm">Уточняющие вопросы</div>
            <div className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              AI-агент обнаружил неоднозначные фрагменты. Выберите действие для каждого.
            </div>
          </div>
        </div>

        {/* Questions */}
        <div className="p-6 space-y-5 max-h-[55vh] overflow-y-auto">
          {questions.map((q, i) => (
            <div key={q.id} className="space-y-2.5">
              <div className="flex items-start gap-2.5">
                <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0 mt-0.5"
                  style={{ background: 'var(--secondary)', color: 'var(--muted-foreground)' }}>
                  {i + 1}
                </span>
                <div>
                  <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{q.question}</div>
                  <div className="mt-1 mono text-xs px-2 py-1 rounded border truncate"
                    style={{ background: 'var(--muted)', borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}>
                    …{q.context}…
                  </div>
                </div>
              </div>
              <div className="pl-7 space-y-1.5">
                {q.options.map(opt => (
                  <label key={opt} className="flex items-center gap-2.5 cursor-pointer group">
                    <div
                      className="w-4 h-4 rounded-full border flex items-center justify-center shrink-0 transition-all"
                      style={{
                        borderColor: q.answer === opt ? 'var(--primary)' : 'var(--border)',
                        background: q.answer === opt ? 'var(--primary)' : 'transparent',
                      }}
                    >
                      {q.answer === opt && <div className="w-1.5 h-1.5 rounded-full bg-black" />}
                    </div>
                    <input type="radio" className="sr-only" name={q.id} value={opt}
                      checked={q.answer === opt}
                      onChange={() => onAnswer(q.id, opt)} />
                    <span className="text-xs" style={{ color: 'var(--foreground)' }}>{opt}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t flex justify-end gap-3"
          style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={onConfirm}
            disabled={!allAnswered}
            className="px-5 py-2 rounded font-medium text-sm transition-all disabled:opacity-40"
            style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
          >
            Применить и продолжить →
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step progress indicator
// ---------------------------------------------------------------------------

function StepBreadcrumb({ step }: { step: AppStep }) {
  const steps: { id: AppStep; label: string }[] = [
    { id: 'upload', label: 'Загрузка' },
    { id: 'processing', label: 'Обработка' },
    { id: 'results', label: 'Результат' },
  ];
  const activeIdx = step === 'clarifying' ? 1 : steps.findIndex(s => s.id === step);

  return (
    <div className="flex items-center gap-1">
      {steps.map((s, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        return (
          <div key={s.id} className="flex items-center gap-1">
            <div className="flex items-center gap-1.5">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all"
                style={{
                  background: done ? 'var(--primary)' : active ? 'var(--primary)' : 'var(--secondary)',
                  color: done || active ? 'var(--primary-foreground)' : 'var(--muted-foreground)',
                }}
              >
                {done ? '✓' : i + 1}
              </div>
              <span
                className="text-xs hidden sm:block"
                style={{ color: active ? 'var(--foreground)' : 'var(--muted-foreground)', fontWeight: active ? 600 : 400 }}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className="w-6 h-px mx-1" style={{ background: i < activeIdx ? 'var(--primary)' : 'var(--border)' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upload view
// ---------------------------------------------------------------------------

function UploadView({
  file, dataTypes, isDragging,
  onDragOver, onDragLeave, onDrop, onFileClick, onFileInput, fileInputRef,
  onToggleType, onProcess,
}: {
  file: UploadedFile | null;
  dataTypes: DataTypeOption[];
  isDragging: boolean;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: () => void;
  onDrop: (e: React.DragEvent) => void;
  onFileClick: () => void;
  onFileInput: (e: React.ChangeEvent<HTMLInputElement>) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onToggleType: (id: string) => void;
  onProcess: () => void;
}) {
  const categories = ['personal', 'financial', 'organization'] as const;
  const selectedCount = dataTypes.filter(d => d.selected).length;

  const extIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return '📄';
    if (ext === 'docx' || ext === 'doc') return '📝';
    if (ext === 'xlsx' || ext === 'xls') return '📊';
    return '📁';
  };

  return (
    <div className="flex-1 flex flex-col">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6 flex-1">
        {/* Left: Drop zone */}
        <div className="flex flex-col gap-5">
          <div>
            <h2 className="text-lg font-semibold">Загрузка документа</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--muted-foreground)' }}>
              Поддерживаются форматы PDF (включая сканированные), DOCX, XLSX
            </p>
          </div>

          {/* Drop zone */}
          <div
            onClick={onFileClick}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className="relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed cursor-pointer transition-all py-12 px-6 text-center"
            style={{
              borderColor: isDragging ? 'var(--primary)' : 'var(--border)',
              background: isDragging ? 'rgba(0,201,167,.06)' : 'var(--secondary)',
            }}
          >
            <div className="text-4xl mb-3">
              {file ? extIcon(file.name) : '⬆'}
            </div>
            {file ? (
              <>
                <div className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{file.name}</div>
                <div className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>
                  {fmtBytes(file.size)} · {file.pageCount} стр.
                </div>
                {file.isScanned && (
                  <div className="mt-3 flex items-center gap-1.5 text-xs px-3 py-1 rounded-full"
                    style={{ background: 'rgba(245,158,11,.15)', color: '#f59e0b' }}>
                    <span>🔍</span> Обнаружен сканированный PDF — будет применён OCR
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="font-medium text-sm" style={{ color: 'var(--foreground)' }}>
                  Перетащите файл сюда или нажмите
                </div>
                <div className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>PDF · DOCX · XLSX</div>
                <div className="mt-3 flex gap-2">
                  {['PDF', 'DOCX', 'XLSX'].map(f => (
                    <span key={f} className="mono text-[11px] px-2 py-1 rounded border"
                      style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)', background: 'var(--muted)' }}>
                      .{f.toLowerCase()}
                    </span>
                  ))}
                </div>
              </>
            )}
            <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.xlsx,.xls" className="sr-only" onChange={onFileInput} />
          </div>

          {/* Replace file button */}
          {file && (
            <button
              onClick={onFileClick}
              className="text-sm text-center py-1.5 rounded border transition-colors hover:bg-white/5"
              style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
            >
              Выбрать другой файл
            </button>
          )}

          {/* Process button */}
          {file && (
            <button
              onClick={onProcess}
              disabled={selectedCount === 0}
              className="w-full py-3 rounded-lg font-semibold text-sm transition-all disabled:opacity-40 shadow-lg"
              style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
            >
              Обезличить документ →
            </button>
          )}

          {file && selectedCount === 0 && (
            <p className="text-xs text-center" style={{ color: 'var(--accent)' }}>
              Выберите хотя бы один тип данных для удаления
            </p>
          )}
        </div>

        {/* Right: Data type selector */}
        <div className="flex flex-col gap-4">
          <div>
            <h2 className="text-lg font-semibold">Типы данных для маскировки</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--muted-foreground)' }}>
              Выбрано: <strong style={{ color: 'var(--primary)' }}>{selectedCount}</strong> из {dataTypes.length}
            </p>
          </div>

          {categories.map(cat => {
            const items = dataTypes.filter(d => d.category === cat);
            return (
              <div key={cat}>
                <div className="text-xs font-semibold uppercase tracking-widest mb-2"
                  style={{ color: 'var(--muted-foreground)' }}>
                  {CATEGORY_LABELS[cat]}
                </div>
                <div className="flex flex-wrap gap-2">
                  {items.map(dt => (
                    <button
                      key={dt.id}
                      onClick={() => onToggleType(dt.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded border text-xs font-medium transition-all"
                      style={{
                        borderColor: dt.selected ? dt.color : 'var(--border)',
                        background: dt.selected ? `${dt.color}18` : 'var(--secondary)',
                        color: dt.selected ? dt.color : 'var(--muted-foreground)',
                      }}
                      title={dt.description}
                    >
                      <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ background: dt.selected ? dt.color : 'var(--border)' }}
                      />
                      {dt.label}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}

          {/* Info box */}
          <div className="mt-auto rounded-lg p-4 text-xs space-y-1.5"
            style={{ background: 'var(--secondary)', borderColor: 'var(--border)', border: '1px solid var(--border)' }}>
            <div className="font-semibold" style={{ color: 'var(--foreground)' }}>Как работает обезличивание</div>
            <div style={{ color: 'var(--muted-foreground)' }}>
              AI-агент анализирует документ и заменяет найденные данные маркерами вида <span className="mono" style={{ color: 'var(--primary)' }}>[ФИО_1]</span>.
              Форматирование и структура таблиц сохраняются. Для сканированных PDF автоматически запускается OCR.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Processing view
// ---------------------------------------------------------------------------

function ProcessingView({ steps, file }: { steps: ProcessingStepDef[]; file: UploadedFile | null }) {
  const doneCount = steps.filter(s => s.status === 'done').length;
  const progress = (doneCount / steps.length) * 100;
  const activeStep = steps.find(s => s.status === 'active');

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="w-full max-w-md space-y-8">
        {/* File + progress */}
        <div className="text-center space-y-3">
          <div className="text-4xl">{file?.name.endsWith('.pdf') ? '📄' : file?.name.endsWith('.docx') ? '📝' : '📊'}</div>
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
            return (
              <div
                key={step.id}
                className="flex items-center gap-3 px-4 py-3 rounded-lg transition-all"
                style={{
                  background: isActive ? 'var(--secondary)' : 'transparent',
                  borderLeft: isActive ? '2px solid var(--primary)' : '2px solid transparent',
                }}
              >
                {/* Status icon */}
                <div className="w-5 h-5 shrink-0 flex items-center justify-center">
                  {isDone && <span className="text-sm" style={{ color: 'var(--primary)' }}>✓</span>}
                  {isActive && (
                    <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
                      style={{ borderColor: 'var(--primary)', borderTopColor: 'transparent' }} />
                  )}
                  {isPending && <div className="w-2 h-2 rounded-full" style={{ background: 'var(--border)' }} />}
                </div>
                {/* Label */}
                <div className="flex-1 min-w-0">
                  <div
                    className="text-sm font-medium truncate"
                    style={{ color: isDone ? 'var(--muted-foreground)' : isActive ? 'var(--foreground)' : 'var(--muted-foreground)' }}
                  >
                    {step.label}
                  </div>
                  {isActive && (
                    <div className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>{step.detail}</div>
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

// ---------------------------------------------------------------------------
// Results view
// ---------------------------------------------------------------------------

function ResultsView({
  replacements, questions, document,
  onDownload, onReset,
}: {
  replacements: Replacement[];
  questions: ClarifyingQuestion[];
  document: DocElement[];
  onDownload: (fmt: 'json' | 'csv') => void;
  onReset: () => void;
}) {
  const [tab, setTab] = useState<'preview' | 'report' | 'export'>('preview');

  const byType = useMemo(() => {
    const m: Record<string, number> = {};
    replacements.forEach(r => { m[r.typeLabel] = (m[r.typeLabel] ?? 0) + 1; });
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [replacements]);

  const answeredQs = questions.filter(q => q.answer);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Stats bar */}
      <div className="px-6 py-4 border-b flex flex-wrap gap-4 items-center"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
            style={{ background: 'rgba(0,201,167,.15)', color: 'var(--primary)' }}>✓</div>
          <div>
            <div className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Замен</div>
            <div className="mono font-bold text-lg leading-none" style={{ color: 'var(--primary)' }}>
              {replacements.length}
            </div>
          </div>
        </div>

        <div className="w-px h-8 hidden sm:block" style={{ background: 'var(--border)' }} />

        <div className="flex flex-wrap gap-2">
          {byType.slice(0, 5).map(([type, count]) => (
            <span key={type} className="text-xs px-2.5 py-1 rounded flex items-center gap-1.5"
              style={{ background: 'var(--secondary)', color: 'var(--foreground)' }}>
              <span style={{ color: 'var(--muted-foreground)' }}>{type}</span>
              <span className="mono font-semibold" style={{ color: 'var(--primary)' }}>{count}</span>
            </span>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button onClick={onReset}
            className="text-xs px-3 py-1.5 rounded border transition-colors hover:bg-white/5"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}>
            ← Новый документ
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
        {([
          ['preview', 'Предпросмотр'],
          ['report', `Отчёт (${replacements.length})`],
          ['export', 'Экспорт'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className="px-5 py-3 text-sm font-medium border-b-2 transition-colors"
            style={{
              borderColor: tab === id ? 'var(--primary)' : 'transparent',
              color: tab === id ? 'var(--foreground)' : 'var(--muted-foreground)',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {tab === 'preview' && (
          <div className="max-w-2xl mx-auto">
            <div className="mb-3 text-xs px-3 py-2 rounded flex items-center gap-2"
              style={{ background: 'rgba(0,201,167,.1)', color: '#00c9a7', border: '1px solid rgba(0,201,167,.2)' }}>
              <span>ℹ</span>
              Наведите курсор на маркер <span className="mono font-semibold">[...]</span> чтобы увидеть исходный текст
            </div>
            <DocumentPreview document={document} replacements={replacements} />
          </div>
        )}

        {tab === 'report' && (
          <div className="space-y-4">
            {answeredQs.length > 0 && (
              <div className="rounded-lg border p-4 space-y-2"
                style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
                <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--muted-foreground)' }}>
                  Решения по уточняющим вопросам
                </div>
                {answeredQs.map(q => (
                  <div key={q.id} className="flex items-start gap-2 text-sm">
                    <span style={{ color: 'var(--primary)' }}>✓</span>
                    <div>
                      <span style={{ color: 'var(--muted-foreground)' }}>{q.question}</span>
                      {' → '}
                      <span style={{ color: 'var(--foreground)' }}>{q.answer}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <ReplacementReport replacements={replacements} />
          </div>
        )}

        {tab === 'export' && (
          <div className="max-w-sm mx-auto space-y-4">
            <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
              Скачать обезличенный документ
            </div>

            <div className="rounded-lg border p-4 flex items-center gap-4 transition-colors hover:bg-white/5 cursor-pointer"
              style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
              <div className="text-3xl">📄</div>
              <div>
                <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
                  Обезличенный документ
                </div>
                <div className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                  В исходном формате с подсветкой замен
                </div>
              </div>
              <span className="ml-auto text-xs px-2.5 py-1 rounded"
                style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}>
                Скачать
              </span>
            </div>

            <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
              Отчёт о заменах
            </div>

            <div className="space-y-2">
              {([['JSON', 'json'], ['CSV', 'csv']] as const).map(([label, fmt]) => (
                <button key={fmt} onClick={() => onDownload(fmt)}
                  className="w-full rounded-lg border p-4 flex items-center gap-4 transition-colors hover:bg-white/5"
                  style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
                  <div className="text-2xl">{fmt === 'json' ? '🗂' : '📊'}</div>
                  <div className="text-left">
                    <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
                      Отчёт {label}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                      {replacements.length} замен · структурированный формат
                    </div>
                  </div>
                  <span className="ml-auto text-xs mono"
                    style={{ color: 'var(--muted-foreground)' }}>
                    .{fmt}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root App
// ---------------------------------------------------------------------------

export default function App() {
  const [theme, setTheme] = useState<Theme>('dark');
  const [step, setStep] = useState<AppStep>('upload');
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [dataTypes, setDataTypes] = useState<DataTypeOption[]>(DEFAULT_DATA_TYPES);
  const [processingSteps, setProcessingSteps] = useState<ProcessingStepDef[]>(
    INITIAL_PROCESSING_STEPS.map(s => ({ ...s }))
  );
  const [replacements, setReplacements] = useState<Replacement[]>([]);
  const [questions, setQuestions] = useState<ClarifyingQuestion[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [clarifyingOpen, setClarifyingOpen] = useState(false);
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

  // Apply theme
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile({ name: f.name, size: f.size, mimeType: f.type, isScanned: f.name.toLowerCase().endsWith('.pdf'), pageCount: Math.floor(Math.random() * 7) + 1 });
  }, []);

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile({ name: f.name, size: f.size, mimeType: f.type, isScanned: f.name.toLowerCase().endsWith('.pdf'), pageCount: Math.floor(Math.random() * 7) + 1 });
  }, []);

  const handleToggleType = useCallback((id: string) => {
    setDataTypes(prev => prev.map(d => d.id === id ? { ...d, selected: !d.selected } : d));
  }, []);

  const handleProcess = useCallback(async () => {
    setStep('processing');
    const fresh = INITIAL_PROCESSING_STEPS.map(s => ({ ...s, status: 'pending' as const }));
    setProcessingSteps(fresh);

    for (let i = 0; i < fresh.length; i++) {
      setProcessingSteps(prev => prev.map((s, idx) => idx === i ? { ...s, status: 'active' } : s));
      await new Promise<void>(r => setTimeout(r, fresh[i].durationMs));
      setProcessingSteps(prev => prev.map((s, idx) => idx === i ? { ...s, status: 'done' } : s));
    }

    setReplacements(MOCK_REPLACEMENTS);
    setQuestions(MOCK_QUESTIONS.map(q => ({ ...q })));
    setClarifyingOpen(true);
  }, []);

  const handleAnswer = useCallback((qId: string, answer: string) => {
    setQuestions(prev => prev.map(q => q.id === qId ? { ...q, answer } : q));
  }, []);

  const handleFinalizeClarifying = useCallback(() => {
    setClarifyingOpen(false);
    setStep('results');
  }, []);

  const handleDownload = useCallback((fmt: 'json' | 'csv') => {
    if (fmt === 'json') {
      const blob = new Blob([JSON.stringify(replacements, null, 2)], { type: 'application/json' });
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'anonymization_report.json' });
      a.click();
    } else {
      const rows = [
        '№,Тип данных,Исходный текст,Маркер,Уверенность,Расположение',
        ...replacements.map((r, i) =>
          `${i + 1},"${r.typeLabel}","${r.original}","${r.masked}","${Math.round(r.confidence * 100)}%","${r.location}"`
        ),
      ].join('\n');
      const blob = new Blob(['﻿' + rows], { type: 'text/csv;charset=utf-8' });
      const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'anonymization_report.csv' });
      a.click();
    }
  }, [replacements]);

  const handleReset = useCallback(() => {
    setFile(null);
    setStep('upload');
    setReplacements([]);
    setQuestions([]);
  }, []);

  return (
    <div
      className="min-h-full flex flex-col"
      style={{ background: 'var(--background)', color: 'var(--foreground)' }}
    >
      {/* Header */}
      <header
        className="flex items-center gap-4 px-5 py-3 border-b shrink-0"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}
      >
        {/* Logo */}
        <div className="flex items-center gap-2.5 mr-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
          >
            🔒
          </div>
          <span className="font-semibold text-base tracking-tight">DocMask</span>
        </div>

        {/* Step breadcrumb */}
        <StepBreadcrumb step={step} />

        {/* Right controls */}
        <div className="ml-auto flex items-center gap-2">
          {/* Theme toggle */}
          <button
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            className="w-9 h-9 flex items-center justify-center rounded-lg border transition-colors hover:bg-white/10"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
            title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          {/* Settings */}
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

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {step === 'upload' && (
          <UploadView
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

        {step === 'processing' && (
          <ProcessingView steps={processingSteps} file={file} />
        )}

        {step === 'results' && (
          <ResultsView
            replacements={replacements}
            questions={questions}
            document={MOCK_DOCUMENT}
            onDownload={handleDownload}
            onReset={handleReset}
          />
        )}
      </main>

      {/* Clarifying questions modal */}
      {clarifyingOpen && (
        <ClarifyingModal
          questions={questions}
          onAnswer={handleAnswer}
          onConfirm={handleFinalizeClarifying}
        />
      )}

      {/* Settings drawer */}
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        config={aiConfig}
        onConfigChange={setAIConfig}
      />
    </div>
  );
}
