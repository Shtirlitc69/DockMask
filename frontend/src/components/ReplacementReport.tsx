import { useState } from 'react';
import { confidenceColor } from '../lib/utils';
import type { Replacement } from '../types';

interface Props {
  replacements: Replacement[];
}

export function ReplacementReport({ replacements }: Props) {
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