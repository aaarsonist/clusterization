// Базовые элементы интерфейса в стиле «матового стекла»
import React, { useEffect } from 'react';
import { Loader2, X } from 'lucide-react';
import type { SegmentCode } from '../types';
import { segmentBadgeStyle } from '../utils/clusterColors';

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ');

export const Card: React.FC<{ className?: string; children: React.ReactNode; title?: React.ReactNode; actions?: React.ReactNode }> = ({ className, children, title, actions }) => (
  <section className={cx('dusk-card p-5', className)}>
    {(title || actions) && (
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        {title && <h2 className="text-[17px] font-medium font-display text-[var(--text-main)]">{title}</h2>}
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    )}
    {children}
  </section>
);

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-[var(--accent-primary)] text-[var(--accent-primary-text)] hover:brightness-105 shadow-sm',
  secondary: 'bg-[var(--bg-input)] text-[var(--text-main)] border border-[var(--border-glass)] hover:bg-[var(--bg-card-hover)]',
  danger: 'bg-[var(--accent-coral)] text-white hover:brightness-105',
  ghost: 'text-[var(--text-secondary)] hover:text-[var(--text-main)] hover:bg-[var(--bg-input)]',
};

export const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean; icon?: React.ReactNode }> = ({ variant = 'secondary', loading, icon, className, children, disabled, ...rest }) => (
  <button
    type="button"
    {...rest}
    disabled={disabled || loading}
    className={cx('inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-full text-[13px] font-medium transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed', VARIANTS[variant], className)}
  >
    {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : icon}
    {children}
  </button>
);

export const Badge: React.FC<{ tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'accent'; children: React.ReactNode }> = ({ tone = 'neutral', children }) => {
  const tones = {
    neutral: 'bg-[var(--bg-input)] text-[var(--text-secondary)] border-[var(--border-glass)]',
    success: 'bg-[var(--accent-sage-subtle)] text-[var(--accent-sage)] border-transparent',
    warning: 'bg-[var(--accent-coral-subtle)] text-[var(--accent-coral)] border-transparent',
    danger: 'bg-[var(--accent-coral-subtle)] text-[var(--accent-coral)] border-transparent',
    accent: 'bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] border-transparent',
  };
  return <span className={cx('inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[12px] font-medium whitespace-nowrap', tones[tone])}>{children}</span>;
};

export const SegmentBadge: React.FC<{ code: SegmentCode | null | undefined; label: string | null | undefined }> = ({ code, label }) => (
  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full border text-[12px] font-medium whitespace-nowrap" style={segmentBadgeStyle(code, label ?? undefined)}>
    {label || 'Не сегментирован'}
  </span>
);

export const Spinner: React.FC<{ label?: string }> = ({ label = 'Загрузка данных...' }) => (
  <div className="flex items-center justify-center gap-2 py-10 text-[14px] text-[var(--text-secondary)]">
    <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-primary)]" />
    <span>{label}</span>
  </div>
);

export const EmptyState: React.FC<{ icon?: React.ReactNode; title: string; text?: string; action?: React.ReactNode }> = ({ icon, title, text, action }) => (
  <div className="flex flex-col items-center justify-center text-center gap-2 py-10 px-6">
    {icon && <div className="w-11 h-11 rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] flex items-center justify-center text-[var(--accent-primary)]">{icon}</div>}
    <div className="text-[15px] font-medium font-display">{title}</div>
    {text && <p className="text-[13px] text-[var(--text-secondary)] max-w-md leading-relaxed">{text}</p>}
    {action && <div className="mt-2">{action}</div>}
  </div>
);

export const Kpi: React.FC<{ label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: 'default' | 'success' | 'warning' }> = ({ label, value, hint, tone = 'default' }) => (
  <div className="dusk-card px-5 py-4">
    <div className="text-[13px] text-[var(--text-secondary)]">{label}</div>
    <div className={cx('mt-1 text-[24px] font-medium font-display tabular-nums', tone === 'success' && 'text-[var(--accent-sage)]', tone === 'warning' && 'text-[var(--accent-coral)]')}>{value}</div>
    {hint && <div className="mt-0.5 text-[12px] text-[var(--text-muted)]">{hint}</div>}
  </div>
);

export const Field: React.FC<{ label: string; error?: string; hint?: string; children: React.ReactNode }> = ({ label, error, hint, children }) => (
  <label className="block">
    <span className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">{label}</span>
    {children}
    {error ? <span className="block mt-1 text-[12px] text-[var(--accent-coral)]">{error}</span> : hint ? <span className="block mt-1 text-[12px] text-[var(--text-muted)]">{hint}</span> : null}
  </label>
);

export const inputClass = (invalid = false) => cx('dusk-input w-full px-4 py-2 text-[14px]', invalid && 'border-[var(--accent-coral)]');

export const Tabs = <T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: string }[] }) => (
  <div className="inline-flex flex-wrap gap-1 p-1 rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)]" role="tablist">
    {items.map((item) => (
      <button key={item.id} type="button" role="tab" aria-selected={value === item.id} onClick={() => onChange(item.id)}
        className={cx('px-4 py-1.5 rounded-full text-[13px] font-medium transition-all', value === item.id ? 'bg-[var(--bg-card)] text-[var(--text-main)] shadow-sm' : 'text-[var(--text-secondary)] hover:text-[var(--text-main)]')}>
        {item.label}
      </button>
    ))}
  </div>
);

export const Modal: React.FC<{ open: boolean; onClose: () => void; title: React.ReactNode; subtitle?: React.ReactNode; width?: string; children: React.ReactNode; footer?: React.ReactNode }> = ({ open, onClose, title, subtitle, width = 'max-w-3xl', children, footer }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm" onMouseDown={onClose} role="dialog" aria-modal="true">
      <div className={cx('dusk-card w-full max-h-[92vh] flex flex-col', width)} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-[var(--border-glass)]">
          <div>
            <h2 className="text-[18px] font-medium font-display">{title}</h2>
            {subtitle && <div className="mt-0.5 text-[13px] text-[var(--text-secondary)]">{subtitle}</div>}
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="w-8 h-8 rounded-full flex items-center justify-center text-[var(--text-secondary)] hover:bg-[var(--bg-input)]"><X className="w-4 h-4" /></button>
        </div>
        <div className="px-6 py-5 overflow-y-auto">{children}</div>
        {footer && <div className="px-6 py-4 border-t border-[var(--border-glass)] flex flex-wrap justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

export const Th: React.FC<{ children?: React.ReactNode; align?: 'left' | 'right' | 'center' }> = ({ children, align = 'left' }) => (
  <th scope="col" className={cx('py-3 px-4 font-medium text-[12px] text-[var(--text-muted)] bg-[var(--bg-input)]', align === 'right' && 'text-right', align === 'center' && 'text-center')}>{children}</th>
);

export const Td: React.FC<{ children?: React.ReactNode; align?: 'left' | 'right' | 'center'; className?: string }> = ({ children, align = 'left', className }) => (
  <td className={cx('py-3 px-4 text-[14px] border-t border-[var(--border-glass)]', align === 'right' && 'text-right tabular-nums whitespace-nowrap', align === 'center' && 'text-center', className)}>{children}</td>
);

export const TableWrap: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="overflow-x-auto rounded-xl border border-[var(--border-glass)]">
    <table className="w-full text-left border-collapse">{children}</table>
  </div>
);
