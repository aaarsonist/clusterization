import React, { createContext, useContext, useState, useCallback, useMemo, useRef } from 'react';
import { CheckCircle2, Info, AlertTriangle, AlertCircle, X, ArrowRight } from 'lucide-react';

export type ToastType = 'success' | 'info' | 'error' | 'warning';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  title?: string;
  message: string;
  type?: ToastType;
  duration?: number; // ms, default 4500
  action?: ToastAction;
}

export interface ToastItem extends ToastOptions {
  id: string;
  type: ToastType;
  isLeaving?: boolean;
}

interface ToastContextType {
  addToast: (options: ToastOptions | string, type?: ToastType) => string;
  success: (message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => string;
  info: (message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => string;
  error: (message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => string;
  warning: (message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => string;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastTimers = useRef<Map<string, { dismissTimer: NodeJS.Timeout; removeTimer?: NodeJS.Timeout }>>(new Map());

  const removeToastImmediate = useCallback((id: string) => {
    const timers = toastTimers.current.get(id);
    if (timers) {
      clearTimeout(timers.dismissTimer);
      if (timers.removeTimer) clearTimeout(timers.removeTimer);
      toastTimers.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, isLeaving: true } : t))
    );
    const removeTimer = setTimeout(() => {
      removeToastImmediate(id);
    }, 280);

    const existing = toastTimers.current.get(id);
    if (existing) {
      existing.removeTimer = removeTimer;
    }
  }, [removeToastImmediate]);

  const addToast = useCallback((options: ToastOptions | string, explicitType?: ToastType): string => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const toastObj: ToastOptions = typeof options === 'string'
      ? { message: options, type: explicitType || 'info' }
      : { ...options, type: options.type || explicitType || 'info' };

    const type = toastObj.type || 'info';
    const duration = toastObj.duration !== undefined ? toastObj.duration : 4500;

    const newToast: ToastItem = {
      ...toastObj,
      id,
      type,
      isLeaving: false,
    };

    setToasts((prev) => [...prev, newToast]);

    if (duration > 0) {
      const dismissTimer = setTimeout(() => {
        removeToast(id);
      }, duration);

      toastTimers.current.set(id, { dismissTimer });
    }

    return id;
  }, [removeToast]);

  const success = useCallback((message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => {
    return addToast({ ...options, message, type: 'success' });
  }, [addToast]);

  const info = useCallback((message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => {
    return addToast({ ...options, message, type: 'info' });
  }, [addToast]);

  const error = useCallback((message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => {
    return addToast({ ...options, message, type: 'error' });
  }, [addToast]);

  const warning = useCallback((message: string, options?: Omit<ToastOptions, 'message' | 'type'>) => {
    return addToast({ ...options, message, type: 'warning' });
  }, [addToast]);

  // Стабильная ссылка на API уведомлений: не вызывает повторных эффектов у потребителей
  const value = useMemo(() => ({ addToast, success, info, error, warning, removeToast }), [addToast, success, info, error, warning, removeToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}

      {/* Парящие стеклянные уведомления Dusk */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="fixed top-6 right-6 z-50 flex flex-col gap-3 max-w-md w-full pointer-events-none px-4 sm:px-0"
      >
        {toasts.map((toast) => {
          const iconColorClass =
            toast.type === 'success'
              ? 'text-[var(--accent-sage)]'
              : toast.type === 'error' || toast.type === 'warning'
              ? 'text-[var(--accent-coral)]'
              : 'text-[var(--accent-primary)]';

          const defaultTitle =
            toast.title ||
            (toast.type === 'success'
              ? 'Успешно'
              : toast.type === 'error'
              ? 'Ошибка'
              : toast.type === 'warning'
              ? 'Внимание'
              : 'Информация');

          return (
            <div
              key={toast.id}
              role="status"
              className={`pointer-events-auto rounded-2xl bg-[var(--bg-card)] backdrop-blur-xl border border-[var(--border-glass)] shadow-sm dark:shadow-[0_8px_32px_rgba(0,0,0,0.36)] text-[var(--text-main)] p-4 flex flex-col gap-2 transition-all duration-300 ease-out transform ${
                toast.isLeaving
                  ? 'opacity-0 translate-x-6 scale-95'
                  : 'opacity-100 translate-x-0 scale-100'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className={`shrink-0 mt-0.5 ${iconColorClass}`}>
                    {toast.type === 'success' && <CheckCircle2 className="w-4 h-4" />}
                    {toast.type === 'error' && <AlertCircle className="w-4 h-4" />}
                    {toast.type === 'warning' && <AlertTriangle className="w-4 h-4" />}
                    {toast.type === 'info' && <Info className="w-4 h-4" />}
                  </div>

                  <div className="min-w-0 space-y-0.5">
                    <div className="text-[13px] font-display font-medium text-[var(--text-main)]">
                      {defaultTitle}
                    </div>
                    <div className="text-[13px] leading-relaxed font-body text-[var(--text-secondary)] [text-wrap:pretty]">
                      {toast.message}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => removeToast(toast.id)}
                  aria-label="Закрыть уведомление"
                  className="shrink-0 w-6 h-6 rounded-full bg-[var(--bg-input)] hover:bg-[var(--bg-card-hover)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-main)] transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {toast.action && (
                <div className="pl-6 pt-1 flex justify-start">
                  <button
                    type="button"
                    onClick={() => {
                      toast.action?.onClick();
                      removeToast(toast.id);
                    }}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] hover:brightness-105 shadow-sm transition-all duration-150 active:scale-[0.98]"
                  >
                    <span>{toast.action.label}</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextType => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast должен использоваться внутри ToastProvider');
  }
  return context;
};
