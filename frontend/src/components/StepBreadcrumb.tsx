import type { AppStep } from '../types';

export function StepBreadcrumb({ step }: { step: AppStep }) {
  const steps: { id: AppStep; label: string }[] = [
    { id: 'upload', label: 'Загрузка' },
    { id: 'processing', label: 'Обработка' },
    { id: 'results', label: 'Результат' },
  ];
  const activeIdx = step === 'clarification' ? 1 : steps.findIndex(s => s.id === step);

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