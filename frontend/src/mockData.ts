import type {
  DocElement,
  DocTableCell,
  Replacement,
  ClarifyingQuestion,
  ProcessingStepDef,
  DataTypeOption,
} from './types';

// ---------------------------------------------------------------------------
// Document content: realistic Russian invoice with inline replacement markers
// ---------------------------------------------------------------------------

function cell(text: string, opts?: { header?: boolean; align?: 'left' | 'center' | 'right'; repId?: string }): DocTableCell {
  return {
    segments: opts?.repId ? [{ text, replacementId: opts.repId }] : [{ text }],
    header: opts?.header,
    align: opts?.align,
  };
}

export const MOCK_DOCUMENT: DocElement[] = [
  { id: 'title', type: 'title', centered: true, bold: true, segments: [{ text: 'СЧЁТ-ФАКТУРА № СФ-2024-0891' }] },
  { id: 'date', type: 'subtitle', centered: true, segments: [{ text: 'от 15 марта 2024 г.' }] },
  { id: 'sp1', type: 'spacer', segments: [] },
  { id: 'div1', type: 'divider', segments: [] },
  { id: 'sp2', type: 'spacer', segments: [] },

  { id: 'sup-lbl', type: 'label', bold: true, segments: [{ text: 'ПОСТАВЩИК' }] },
  {
    id: 'sup-name', type: 'field', segments: [
      { text: 'Наименование: ' },
      { text: 'ООО «ТехноСервис»', replacementId: 'r1' },
    ],
  },
  {
    id: 'sup-inn', type: 'field', segments: [
      { text: 'ИНН / КПП: ' },
      { text: '7712345678', replacementId: 'r2' },
      { text: ' / ' },
      { text: '771201001', replacementId: 'r3' },
    ],
  },
  {
    id: 'sup-ogrn', type: 'field', segments: [
      { text: 'ОГРН: ' },
      { text: '1197746823451', replacementId: 'r4' },
    ],
  },
  {
    id: 'sup-addr', type: 'field', segments: [
      { text: 'Адрес: ' },
      { text: '125009, г. Москва, ул. Большая Никитская, д. 22, офис 301', replacementId: 'r5' },
    ],
  },
  {
    id: 'sup-phone', type: 'field', segments: [
      { text: 'Телефон: ' },
      { text: '+7 (495) 644-12-89', replacementId: 'r6' },
    ],
  },
  {
    id: 'sup-email', type: 'field', segments: [
      { text: 'E-mail: ' },
      { text: 'finance@technoservis.ru', replacementId: 'r7' },
    ],
  },
  {
    id: 'sup-bank', type: 'field', segments: [
      { text: 'Р/с: ' },
      { text: '40702810500234567891', replacementId: 'r8' },
      { text: ' в АО «Альфа-Банк», БИК ' },
      { text: '044525593', replacementId: 'r9' },
    ],
  },

  { id: 'sp3', type: 'spacer', segments: [] },
  { id: 'div2', type: 'divider', segments: [] },
  { id: 'sp4', type: 'spacer', segments: [] },

  { id: 'buy-lbl', type: 'label', bold: true, segments: [{ text: 'ПОКУПАТЕЛЬ' }] },
  {
    id: 'buy-name', type: 'field', segments: [
      { text: 'ФИО: ' },
      { text: 'Иванов Иван Иванович', replacementId: 'r10' },
    ],
  },
  {
    id: 'buy-dob', type: 'field', segments: [
      { text: 'Дата рождения: ' },
      { text: '12.05.1985', replacementId: 'r11' },
    ],
  },
  {
    id: 'buy-pass', type: 'field', segments: [
      { text: 'Паспорт: ' },
      { text: '4520 789123', replacementId: 'r12' },
      { text: ', выдан ОВД Пресненского р-на г. Москвы 20.06.2005' },
    ],
  },
  {
    id: 'buy-inn', type: 'field', segments: [
      { text: 'ИНН: ' },
      { text: '772987654321', replacementId: 'r13' },
    ],
  },
  {
    id: 'buy-snils', type: 'field', segments: [
      { text: 'СНИЛС: ' },
      { text: '123-456-789 01', replacementId: 'r14' },
    ],
  },
  {
    id: 'buy-addr', type: 'field', segments: [
      { text: 'Адрес: ' },
      { text: '123112, г. Москва, Пресненская наб., д. 8, стр. 1, кв. 421', replacementId: 'r15' },
    ],
  },
  {
    id: 'buy-phone', type: 'field', segments: [
      { text: 'Телефон: ' },
      { text: '+7 (916) 234-78-90', replacementId: 'r16' },
    ],
  },
  {
    id: 'buy-email', type: 'field', segments: [
      { text: 'E-mail: ' },
      { text: 'ivan.ivanov.1985@gmail.com', replacementId: 'r17' },
    ],
  },

  { id: 'sp5', type: 'spacer', segments: [] },
  { id: 'div3', type: 'divider', segments: [] },
  { id: 'sp6', type: 'spacer', segments: [] },

  {
    id: 'table1',
    type: 'table',
    rows: [
      [
        cell('№', { header: true, align: 'center' }),
        cell('Наименование товара / услуги', { header: true }),
        cell('Кол-во', { header: true, align: 'center' }),
        cell('Ед.', { header: true, align: 'center' }),
        cell('Цена, руб.', { header: true, align: 'right' }),
        cell('Сумма, руб.', { header: true, align: 'right' }),
      ],
      [
        cell('1', { align: 'center' }),
        cell('Техническое обслуживание серверного оборудования'),
        cell('1', { align: 'center' }),
        cell('усл.', { align: 'center' }),
        cell('85 000,00', { align: 'right' }),
        cell('85 000,00', { align: 'right' }),
      ],
      [
        cell('2', { align: 'center' }),
        cell('Лицензия ПО «DataGuard Pro» (12 мес.)'),
        cell('3', { align: 'center' }),
        cell('шт.', { align: 'center' }),
        cell('12 500,00', { align: 'right' }),
        cell('37 500,00', { align: 'right' }),
      ],
      [
        cell('3', { align: 'center' }),
        cell('Консультационные услуги (40 ч. × 2 500,00 руб.)'),
        cell('40', { align: 'center' }),
        cell('час', { align: 'center' }),
        cell('2 500,00', { align: 'right' }),
        cell('100 000,00', { align: 'right' }),
      ],
    ],
  } as DocElement,

  { id: 'sp7', type: 'spacer', segments: [] },

  {
    id: 'tot1', type: 'field', segments: [
      { text: 'Итого без НДС: ' },
      { text: '222 500,00 руб.', replacementId: 'r18' },
    ],
  },
  {
    id: 'tot2', type: 'field', segments: [
      { text: 'НДС 20%: ' },
      { text: '44 500,00 руб.', replacementId: 'r19' },
    ],
  },
  {
    id: 'tot3', type: 'field', bold: true, segments: [
      { text: 'ИТОГО К ОПЛАТЕ: ' },
      { text: '267 000,00 руб.', replacementId: 'r20' },
    ],
  },

  { id: 'sp8', type: 'spacer', segments: [] },
  {
    id: 'note', type: 'text', segments: [
      { text: 'Оплата по договору № КД-2024/15 от 01.03.2024 г. в течение 10 банковских дней с момента выставления счёта.' },
    ],
  },
  { id: 'sp9', type: 'spacer', segments: [] },
  { id: 'div4', type: 'divider', segments: [] },
  { id: 'sp10', type: 'spacer', segments: [] },

  {
    id: 'sig1', type: 'field', segments: [
      { text: 'Подпись поставщика: ' },
      { text: 'Петров Сергей Алексеевич', replacementId: 'r21' },
      { text: ', Генеральный директор' },
    ],
  },
  {
    id: 'sig2', type: 'field', segments: [
      { text: 'Подпись покупателя: ' },
      { text: 'Иванов И.И.', replacementId: 'r22' },
    ],
  },
];

// ---------------------------------------------------------------------------
// Replacement manifest
// ---------------------------------------------------------------------------

export const MOCK_REPLACEMENTS: Replacement[] = [
  { id: 'r1',  original: 'ООО «ТехноСервис»', masked: '[ОРГАНИЗАЦИЯ_1]', typeId: 'org_name',    typeLabel: 'Наим. организации', confidence: 0.99, location: 'Блок «Поставщик»' },
  { id: 'r2',  original: '7712345678',         masked: '[ИНН_1]',         typeId: 'inn',         typeLabel: 'ИНН',               confidence: 0.99, location: 'Блок «Поставщик»' },
  { id: 'r3',  original: '771201001',           masked: '[КПП_1]',         typeId: 'kpp',         typeLabel: 'КПП',               confidence: 0.99, location: 'Блок «Поставщик»' },
  { id: 'r4',  original: '1197746823451',       masked: '[ОГРН_1]',        typeId: 'ogrn',        typeLabel: 'ОГРН',              confidence: 0.98, location: 'Блок «Поставщик»' },
  { id: 'r5',  original: '125009, г. Москва, ул. Большая Никитская, д. 22, офис 301', masked: '[АДРЕС_1]', typeId: 'address', typeLabel: 'Адрес', confidence: 0.97, location: 'Блок «Поставщик»' },
  { id: 'r6',  original: '+7 (495) 644-12-89',  masked: '[ТЕЛЕФОН_1]',    typeId: 'phone',       typeLabel: 'Телефон',           confidence: 1.00, location: 'Блок «Поставщик»' },
  { id: 'r7',  original: 'finance@technoservis.ru', masked: '[EMAIL_1]',  typeId: 'email',       typeLabel: 'Email',             confidence: 1.00, location: 'Блок «Поставщик»' },
  { id: 'r8',  original: '40702810500234567891',masked: '[СЧЁТ_1]',       typeId: 'bank_account',typeLabel: 'Расч. счёт',        confidence: 0.99, location: 'Блок «Поставщик»' },
  { id: 'r9',  original: '044525593',           masked: '[БИК_1]',         typeId: 'bik',         typeLabel: 'БИК',               confidence: 0.99, location: 'Блок «Поставщик»' },
  { id: 'r10', original: 'Иванов Иван Иванович',masked: '[ФИО_1]',        typeId: 'fio',         typeLabel: 'ФИО',               confidence: 0.99, location: 'Блок «Покупатель»' },
  { id: 'r11', original: '12.05.1985',          masked: '[ДАТА_РОЖД_1]',  typeId: 'dob',         typeLabel: 'Дата рождения',     confidence: 0.97, location: 'Блок «Покупатель»' },
  { id: 'r12', original: '4520 789123',         masked: '[ПАСПОРТ_1]',    typeId: 'passport',    typeLabel: 'Паспорт',           confidence: 0.99, location: 'Блок «Покупатель»' },
  { id: 'r13', original: '772987654321',        masked: '[ИНН_2]',         typeId: 'inn',         typeLabel: 'ИНН',               confidence: 0.99, location: 'Блок «Покупатель»' },
  { id: 'r14', original: '123-456-789 01',      masked: '[СНИЛС_1]',      typeId: 'snils',       typeLabel: 'СНИЛС',             confidence: 0.99, location: 'Блок «Покупатель»' },
  { id: 'r15', original: '123112, г. Москва, Пресненская наб., д. 8, стр. 1, кв. 421', masked: '[АДРЕС_2]', typeId: 'address', typeLabel: 'Адрес', confidence: 0.98, location: 'Блок «Покупатель»' },
  { id: 'r16', original: '+7 (916) 234-78-90',  masked: '[ТЕЛЕФОН_2]',    typeId: 'phone',       typeLabel: 'Телефон',           confidence: 1.00, location: 'Блок «Покупатель»' },
  { id: 'r17', original: 'ivan.ivanov.1985@gmail.com', masked: '[EMAIL_2]',typeId: 'email',      typeLabel: 'Email',             confidence: 1.00, location: 'Блок «Покупатель»' },
  { id: 'r18', original: '222 500,00 руб.',     masked: '[СУММА_1]',      typeId: 'amount',      typeLabel: 'Фин. сумма',        confidence: 0.96, location: 'Итоги' },
  { id: 'r19', original: '44 500,00 руб.',      masked: '[СУММА_2]',      typeId: 'amount',      typeLabel: 'Фин. сумма',        confidence: 0.96, location: 'Итоги' },
  { id: 'r20', original: '267 000,00 руб.',     masked: '[СУММА_3]',      typeId: 'amount',      typeLabel: 'Фин. сумма',        confidence: 0.97, location: 'Итоги' },
  { id: 'r21', original: 'Петров Сергей Алексеевич', masked: '[ФИО_2]',  typeId: 'fio',         typeLabel: 'ФИО',               confidence: 0.99, location: 'Подписи' },
  { id: 'r22', original: 'Иванов И.И.',         masked: '[ФИО_3]',        typeId: 'fio',         typeLabel: 'ФИО',               confidence: 0.97, location: 'Подписи' },
];

// ---------------------------------------------------------------------------
// Clarifying questions from the AI agent
// ---------------------------------------------------------------------------

export const MOCK_QUESTIONS: ClarifyingQuestion[] = [
  {
    id: 'q1',
    question: 'Обнаружен номер договора «КД-2024/15». Маскировать?',
    context: 'Оплата по договору № КД-2024/15 от 01.03.2024 г. в течение 10 банковских дней.',
    options: ['Да — заменить на [ДОГОВОР_1]', 'Нет — оставить как есть', 'Маскировать только номер, дату оставить'],
  },
  {
    id: 'q2',
    question: 'Название ПО «DataGuard Pro» в таблице — конфиденциально?',
    context: 'Лицензия ПО «DataGuard Pro» (12 мес.) — строка 2 таблицы.',
    options: ['Да — заменить на [ПРОДУКТ_1]', 'Нет — публичное коммерческое название'],
  },
  {
    id: 'q3',
    question: 'Маскировать «АО «Альфа-Банк»» — публичная организация?',
    context: '40702810500234567891 в АО «Альфа-Банк», БИК 044525593',
    options: ['Да — заменить на [БАНК_1]', 'Нет — публично известная организация'],
  },
];

// ---------------------------------------------------------------------------
// Processing steps simulation
// ---------------------------------------------------------------------------

export const INITIAL_PROCESSING_STEPS: ProcessingStepDef[] = [
  { id: 's1', label: 'Извлечение структуры документа',   detail: 'Метаданные, шрифты, таблицы, разметка',      status: 'pending', durationMs: 1100 },
  { id: 's2', label: 'Определение типа документа',       detail: 'Счёт-фактура / договор / акт...',            status: 'pending', durationMs: 700  },
  { id: 's3', label: 'Обнаружение сканированных страниц',detail: 'Вектор vs растровое содержимое',             status: 'pending', durationMs: 550  },
  { id: 's4', label: 'OCR-распознавание текста',         detail: 'Tesseract 5 + Russian LSTM model',           status: 'pending', durationMs: 2200 },
  { id: 's5', label: 'Анализ конфиденциальных данных',   detail: 'NER + AI-агент (GigaChat-Pro)',               status: 'pending', durationMs: 3000 },
  { id: 's6', label: 'Применение масок',                 detail: 'Замена с сохранением форматирования',        status: 'pending', durationMs: 900  },
  { id: 's7', label: 'Проверка полноты обезличивания',   detail: 'Валидация остаточных персональных данных',   status: 'pending', durationMs: 750  },
  { id: 's8', label: 'Генерация отчёта',                 detail: 'JSON + CSV экспорт',                         status: 'pending', durationMs: 380  },
];

// ---------------------------------------------------------------------------
// Default data type options
// ---------------------------------------------------------------------------

export const DEFAULT_DATA_TYPES: DataTypeOption[] = [
  // Personal
  { id: 'fio',         label: 'ФИО',           description: 'Имена физических лиц',              category: 'personal',     markerPrefix: 'ФИО',          selected: true,  color: '#3b82f6' },
  { id: 'dob',         label: 'Дата рождения', description: 'Даты рождения',                     category: 'personal',     markerPrefix: 'ДАТА_РОЖД',    selected: true,  color: '#3b82f6' },
  { id: 'passport',    label: 'Паспорт',       description: 'Серия и номер паспорта',            category: 'personal',     markerPrefix: 'ПАСПОРТ',      selected: true,  color: '#3b82f6' },
  { id: 'snils',       label: 'СНИЛС',         description: 'СНИЛС физического лица',            category: 'personal',     markerPrefix: 'СНИЛС',        selected: true,  color: '#3b82f6' },
  { id: 'address',     label: 'Адрес',         description: 'Почтовые и жилые адреса',           category: 'personal',     markerPrefix: 'АДРЕС',        selected: true,  color: '#8b5cf6' },
  { id: 'phone',       label: 'Телефон',       description: 'Номера телефонов',                  category: 'personal',     markerPrefix: 'ТЕЛЕФОН',      selected: true,  color: '#8b5cf6' },
  { id: 'email',       label: 'Email',         description: 'Адреса электронной почты',          category: 'personal',     markerPrefix: 'EMAIL',        selected: true,  color: '#8b5cf6' },
  // Financial
  { id: 'inn',         label: 'ИНН',           description: 'ИНН физ. и юр. лиц',               category: 'financial',    markerPrefix: 'ИНН',          selected: true,  color: '#f59e0b' },
  { id: 'kpp',         label: 'КПП',           description: 'КПП организации',                   category: 'financial',    markerPrefix: 'КПП',          selected: true,  color: '#f59e0b' },
  { id: 'ogrn',        label: 'ОГРН',          description: 'ОГРН / ОГРНИП',                     category: 'financial',    markerPrefix: 'ОГРН',         selected: false, color: '#f59e0b' },
  { id: 'bank_account',label: 'Расч. счёт',    description: 'Расчётные счета',                   category: 'financial',    markerPrefix: 'СЧЁТ',         selected: true,  color: '#f59e0b' },
  { id: 'bik',         label: 'БИК',           description: 'БИК банка',                         category: 'financial',    markerPrefix: 'БИК',          selected: false, color: '#f59e0b' },
  { id: 'amount',      label: 'Суммы',         description: 'Финансовые суммы и цены',           category: 'financial',    markerPrefix: 'СУММА',        selected: false, color: '#10b981' },
  // Organization
  { id: 'org_name',    label: 'Назв. орг.',    description: 'Наименования юридических лиц',      category: 'organization', markerPrefix: 'ОРГАНИЗАЦИЯ',  selected: true,  color: '#ef4444' },
];
