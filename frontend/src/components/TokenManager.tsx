import { useState } from 'react';
import type { TokenEntry, AIProviderType } from '../types';
import { PROVIDER_META } from '../lib/aiProvider';

const INITIAL_TOKENS: TokenEntry[] = [
  {
    id: '1',
    label: 'GigaChat Production',
    provider: 'gigachat',
    maskedToken: 'MDY0Y2...VVc=',
    fullToken: '',
    isActive: true,
    createdAt: '2024-03-15',
  },
];

interface Props {
  onTokenActivate?: (token: TokenEntry) => void;
}

export default function TokenManager({ onTokenActivate }: Props) {
  const [tokens, setTokens] = useState<TokenEntry[]>(INITIAL_TOKENS);
  const [showForm, setShowForm] = useState(false);
  const [revealId, setRevealId] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [form, setForm] = useState({ label: '', provider: 'gigachat' as AIProviderType, fullToken: '' });

  const handleAdd = () => {
    if (!form.label.trim() || !form.fullToken.trim()) return;
    const t = form.fullToken.trim();
    const entry: TokenEntry = {
      id: Date.now().toString(),
      label: form.label.trim(),
      provider: form.provider,
      maskedToken: t.slice(0, 5) + '...' + t.slice(-4),
      fullToken: t,
      isActive: false,
      createdAt: new Date().toISOString().slice(0, 10),
    };
    setTokens(prev => [...prev, entry]);
    setForm({ label: '', provider: 'gigachat', fullToken: '' });
    setShowForm(false);
  };

  const handleActivate = (id: string) => {
    setTokens(prev => prev.map(t => ({ ...t, isActive: t.id === id })));
    const t = tokens.find(t => t.id === id);
    if (t) onTokenActivate?.(t);
  };

  const handleDelete = (id: string) => {
    setTokens(prev => prev.filter(t => t.id !== id));
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(id);
    setTimeout(() => setCopied(null), 1800);
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: 'var(--muted-foreground)' }}>
          Токены доступа
        </span>
        <button
          onClick={() => setShowForm(v => !v)}
          className="text-xs px-3 py-1 rounded font-medium transition-all"
          style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
        >
          {showForm ? '✕ Отмена' : '+ Добавить'}
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="rounded border p-3 space-y-2.5 animate-in"
          style={{ background: 'var(--secondary)', borderColor: 'var(--border)' }}>
          <div className="space-y-1">
            <label className="block text-xs" style={{ color: 'var(--muted-foreground)' }}>Название</label>
            <input
              value={form.label}
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))}
              placeholder="Производственный токен GigaChat"
              className="w-full text-sm px-2.5 py-1.5 rounded border outline-none transition-colors focus:border-current"
              style={{ background: 'var(--background)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
            />
          </div>
          <div className="space-y-1">
            <label className="block text-xs" style={{ color: 'var(--muted-foreground)' }}>Провайдер</label>
            <select
              value={form.provider}
              onChange={e => setForm(f => ({ ...f, provider: e.target.value as AIProviderType }))}
              className="w-full text-sm px-2.5 py-1.5 rounded border outline-none"
              style={{ background: 'var(--background)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
            >
              {(Object.entries(PROVIDER_META) as [AIProviderType, typeof PROVIDER_META[AIProviderType]][]).map(([id, m]) => (
                <option key={id} value={id}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="block text-xs" style={{ color: 'var(--muted-foreground)' }}>API-токен / ключ</label>
            <input
              type="password"
              value={form.fullToken}
              onChange={e => setForm(f => ({ ...f, fullToken: e.target.value }))}
              placeholder="Bearer token или sk-..."
              className="w-full text-sm px-2.5 py-1.5 rounded border outline-none mono"
              style={{ background: 'var(--background)', borderColor: 'var(--border)', color: 'var(--foreground)' }}
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={!form.label.trim() || !form.fullToken.trim()}
            className="w-full text-sm py-1.5 rounded font-medium transition-all disabled:opacity-40"
            style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
          >
            Сохранить токен
          </button>
        </div>
      )}

      {/* Token list */}
      <div className="space-y-2">
        {tokens.map(token => (
          <div
            key={token.id}
            className="rounded border p-3 transition-all"
            style={{
              background: 'var(--secondary)',
              borderColor: token.isActive ? 'var(--primary)' : 'var(--border)',
            }}
          >
            <div className="flex items-start gap-2">
              {/* Status dot */}
              <div className="mt-0.5 shrink-0">
                <div
                  className="w-2 h-2 rounded-full mt-1"
                  style={{ background: token.isActive ? 'var(--success, #10b981)' : 'var(--border)' }}
                />
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium truncate" style={{ color: 'var(--foreground)' }}>
                    {token.label}
                  </span>
                  {token.isActive && (
                    <span className="text-xs px-1.5 py-0.5 rounded"
                      style={{ background: 'rgba(0,201,167,.15)', color: 'var(--primary)' }}>
                      активен
                    </span>
                  )}
                </div>
                <div className="mt-0.5 flex items-center gap-2 flex-wrap">
                  <span className="text-xs px-1.5 py-0.5 rounded"
                    style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>
                    {PROVIDER_META[token.provider]?.label ?? token.provider}
                  </span>
                  <span className="mono text-xs" style={{ color: 'var(--muted-foreground)' }}>
                    {revealId === token.id && token.fullToken ? token.fullToken : token.maskedToken}
                  </span>
                </div>
                <div className="mt-1 text-xs" style={{ color: 'var(--muted-foreground)' }}>
                  Добавлен {token.createdAt}
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => setRevealId(revealId === token.id ? null : token.id)}
                  title={revealId === token.id ? 'Скрыть' : 'Показать'}
                  className="w-7 h-7 flex items-center justify-center rounded text-sm transition-colors hover:bg-white/10"
                  style={{ color: 'var(--muted-foreground)' }}
                >
                  {revealId === token.id ? '🙈' : '👁'}
                </button>
                <button
                  onClick={() => handleCopy(token.fullToken || token.maskedToken, token.id)}
                  title="Копировать"
                  className="w-7 h-7 flex items-center justify-center rounded text-sm transition-colors hover:bg-white/10"
                  style={{ color: copied === token.id ? 'var(--primary)' : 'var(--muted-foreground)' }}
                >
                  {copied === token.id ? '✓' : '📋'}
                </button>
                {!token.isActive && (
                  <button
                    onClick={() => handleActivate(token.id)}
                    className="text-xs px-2 py-1 rounded font-medium transition-all"
                    style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
                  >
                    Выбрать
                  </button>
                )}
                <button
                  onClick={() => handleDelete(token.id)}
                  title="Удалить"
                  className="w-7 h-7 flex items-center justify-center rounded text-sm transition-colors hover:bg-red-500/20"
                  style={{ color: 'var(--muted-foreground)' }}
                >
                  🗑
                </button>
              </div>
            </div>
          </div>
        ))}

        {tokens.length === 0 && (
          <div className="py-6 text-center text-sm" style={{ color: 'var(--muted-foreground)' }}>
            Нет сохранённых токенов
          </div>
        )}
      </div>
    </div>
  );
}
