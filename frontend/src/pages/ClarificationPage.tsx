import type { ClarifyingQuestion } from '../types';

interface Props {
  questions: ClarifyingQuestion[];
  onAnswer: (qId: string, answer: string) => void;
  onConfirm: () => void;
}

export function ClarificationPage({ questions, onAnswer, onConfirm }: Props) {
  const allAnswered = questions.every(q => q.answer);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b flex items-center justify-between"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-lg shrink-0 mt-0.5"
            style={{ background: 'rgba(245,158,11,.15)', color: '#f59e0b' }}>
            ?
          </div>
          <div>
            <h2 className="font-semibold text-base" style={{ color: 'var(--foreground)' }}>
              Уточняющие вопросы
            </h2>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              AI-агент обнаружил неоднозначные фрагменты. Выберите действие для каждого.
            </p>
          </div>
        </div>
      </div>

      {/* Questions */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto space-y-5">
          {questions.map((q, i) => (
            <div key={q.id} className="rounded-lg border p-5 space-y-2.5"
              style={{ background: 'var(--card)', borderColor: 'var(--border)' }}>
              <div className="flex items-start gap-2.5">
                <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 mt-0.5"
                  style={{ background: 'var(--secondary)', color: 'var(--muted-foreground)' }}>
                  {i + 1}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{q.question}</div>
                  <div className="mt-1 mono text-xs px-2 py-1 rounded border truncate"
                    style={{ background: 'var(--muted)', borderColor: 'var(--border)', color: 'var(--muted-foreground)' }}>
                    …{q.context}…
                  </div>
                </div>
              </div>
              <div className="pl-8 space-y-1.5">
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
                    <span className="text-sm" style={{ color: 'var(--foreground)' }}>{opt}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="px-6 py-4 border-t flex justify-end gap-3"
        style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
        <button
          onClick={onConfirm}
          disabled={!allAnswered}
          className="px-6 py-2.5 rounded-lg font-medium text-sm transition-all disabled:opacity-40"
          style={{ background: 'var(--primary)', color: 'var(--primary-foreground)' }}
        >
          Применить и продолжить →
        </button>
      </div>
    </div>
  );
}