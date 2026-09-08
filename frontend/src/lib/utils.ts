/**
 * Форматирование размера файла в человекочитаемый вид.
 */
export function fmtBytes(b: number): string {
  if (b < 1024) return `${b} Б`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} КБ`;
  return `${(b / 1048576).toFixed(1)} МБ`;
}

/**
 * Возвращает цвет для индикатора уверенности (confidence).
 */
export function confidenceColor(c: number): string {
  if (c >= 0.98) return '#10b981'; // зелёный
  if (c >= 0.93) return '#f59e0b'; // жёлтый
  return '#ef4444';                 // красный
}

/**
 * Русские названия категорий типов данных.
 */
export const CATEGORY_LABELS: Record<string, string> = {
  personal: 'Персональные данные',
  financial: 'Финансовые данные',
  organization: 'Данные организации',
};