// Форматирование значений для русскоязычного интерфейса
import type { AlgorithmId, Money } from '../types';

const nf = (digits: number) => new Intl.NumberFormat('ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const num = (value: number | string | null | undefined, digits = 0): string =>
  value === null || value === undefined || value === '' ? '—' : nf(digits).format(Number(value));

export const money = (value: Money | null | undefined, digits = 2): string =>
  value === null || value === undefined ? '—' : `${nf(digits).format(Number(value))} BYN`;

export const percent = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? '—' : `${nf(digits).format(value)} %`;

export const metric = (value: number | null | undefined, digits = 3): string =>
  value === null || value === undefined ? '—' : nf(digits).format(value);

export const dateTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export const date = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU');
};

export const bytes = (value: number): string => {
  if (value >= 1024 ** 3) return `${num(value / 1024 ** 3, 1)} ГБ`;
  if (value >= 1024 ** 2) return `${num(value / 1024 ** 2, 1)} МБ`;
  return `${num(value / 1024, 0)} КБ`;
};

export const ALGORITHM_NAMES: Record<AlgorithmId, string> = {
  kmeans: 'K-Means++',
  agglomerative: 'Иерархическая (метод Уорда)',
  dbscan: 'DBSCAN (плотностной)',
};

export const plural = (n: number, forms: [string, string, string]): string => {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
};
