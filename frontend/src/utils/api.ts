// HTTP-клиент REST API: токен доступа, обработка ошибок на русском языке, загрузка файлов
import { extractErrorMessage } from './errorUtils';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export const setApiToken = (value: string | null) => { token = value; };
export const setUnauthorizedHandler = (handler: (() => void) | null) => { onUnauthorized = handler; };

async function request(method: string, url: string, body?: unknown, isForm = false): Promise<Response> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Сервис временно недоступен. Проверьте подключение и повторите попытку.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = extractErrorMessage(data, `Ошибка выполнения запроса (код ${response.status})`);
    if (response.status === 401 && onUnauthorized && !url.endsWith('/auth/login')) onUnauthorized();
    throw new ApiError(response.status, message);
  }
  return response;
}

async function json<T>(method: string, url: string, body?: unknown, isForm = false): Promise<T> {
  const response = await request(method, url, body, isForm);
  return (await response.json()) as T;
}

export const api = {
  get: <T>(url: string) => json<T>('GET', url),
  post: <T>(url: string, body?: unknown) => json<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => json<T>('PUT', url, body),
  patch: <T>(url: string, body: unknown) => json<T>('PATCH', url, body),
  del: <T>(url: string) => json<T>('DELETE', url),
  upload: <T>(url: string, form: FormData) => json<T>('POST', url, form, true),
  async download(url: string, fallbackName: string): Promise<string> {
    const response = await request('GET', url);
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename\*=utf-8''([^;]+)/i.exec(disposition) || /filename="?([^";]+)"?/i.exec(disposition);
    const name = match ? decodeURIComponent(match[1]) : fallbackName;
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    return name;
  },
};

export const qs = (params: Record<string, string | number | boolean | null | undefined>): string => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
};
