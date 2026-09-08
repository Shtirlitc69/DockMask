import { useState } from 'react';
import type { Replacement } from '../types';

export function RepBadge({ rep }: { rep: Replacement }) {
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