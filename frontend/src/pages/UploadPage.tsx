import { useCallback, useRef } from 'react';
import type { UploadedFile, DataTypeOption } from '../types';
import { fmtBytes, CATEGORY_LABELS } from '../lib/utils';

interface Props {
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
}

export function UploadPage({
  file, dataTypes, isDragging,
  onDragOver, onDragLeave, onDrop, onFileClick, onFileInput, fileInputRef,
  onToggleType, onProcess,
}: Props) {
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