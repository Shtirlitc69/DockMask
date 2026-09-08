import { useState, useMemo } from 'react';
import { DocumentPreview } from '../components/DocumentPreview';
import { ReplacementReport } from '../components/ReplacementReport';
import type { Replacement, ClarifyingQuestion, DocElement } from '../types';

interface Props {
  replacements: Replacement[];
  questions: ClarifyingQuestion[];
  document: DocElement[];
  onDownload: (fmt: 'json' | 'csv') => void;
  onReset: () => void;
}

export function ResultsPage({
  replacements,
  questions,
  document,
  onDownload,
  onReset,
}: Props) {
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