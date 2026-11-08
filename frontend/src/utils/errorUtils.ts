/**
 * Извлечение понятного текста ошибки из ответа API (формат FastAPI) или исключения.
 * Ошибки валидации выводятся в виде «поле: сообщение».
 */
const FIELD_NAMES: Record<string, string> = {
  username: 'Логин', password: 'Пароль', rule_name: 'Наименование', reward_value: 'Размер поощрения',
  min_check_amount: 'Минимальный чек', days_valid: 'Срок действия', check_amount: 'Сумма чека', days_period: 'Период',
  run_hour: 'Час запуска', retention_count: 'Число хранимых копий', role: 'Роль',
};

export const extractErrorMessage = (err: unknown, fallback = 'Произошла ошибка при выполнении операции'): string => {
  if (!err) return fallback;
  if (typeof err === 'string') return err.trim() || fallback;
  const data = err as { detail?: unknown; message?: unknown };
  if (data.detail !== undefined) {
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item: { field?: string; msg?: string }) => {
          const field = item.field ? FIELD_NAMES[item.field] || item.field : '';
          return field ? `${field}: ${item.msg}` : String(item.msg ?? '');
        })
        .join('; ');
    }
  }
  if (typeof data.message === 'string' && data.message && !data.message.includes('[object Object]')) return data.message;
  return fallback;
};
