import { useState } from 'react';
import TokenManager from '../components/TokenManager';
import { PROVIDER_META } from '../lib/aiProvider';
import type { AIConfig, AIProviderType } from '../types';

interface Props {
  config: AIConfig;
  onChange: (config: AIConfig) => void;
  onClose?: () => void;
}

export function SettingsPage({ config, onChange, onClose }: Props) {
  const meta = PROVIDER_META[config.provider];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b flex items-center justify-between"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
        <div>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--foreground)' }}>
            Настройки
          </h2>
          <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>
            Конфигурация AI-агента и параметры обработки
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-lg border transition-colors hover:bg-white/10"
            style={{ borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-6">
          {/* AI Settings Section */}
          <div className="rounded-lg border p-5 space-y-4"
            style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
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
          </div>

          {/* Token Manager Section */}
          <div className="rounded-lg border p-5"
            style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
            <div className="text-xs font-semibold tracking-widest uppercase mb-4"
              style={{ color: 'var(--muted-foreground)' }}>
              Управление токенами
            </div>
            <TokenManager />
          </div>

          {/* Info Section */}
          <div className="rounded-lg border p-5 text-xs space-y-2"
            style={{ background: 'var(--secondary)', borderColor: 'var(--border)' }}>
            <div className="font-semibold" style={{ color: 'var(--foreground)' }}>
              Как это работает
            </div>
            <div style={{ color: 'var(--muted-foreground)' }}>
              AI-агент анализирует документ и заменяет найденные персональные данные маркерами.
              Настройки выше определяют, какой провайдер и модель будут использоваться для анализа.
              Температура контролирует "креативность" модели —越低 значение, тем более предсказуемы ответы.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}