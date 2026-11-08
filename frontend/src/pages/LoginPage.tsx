import React, { useState } from 'react';
import { AlertCircle, ArrowRight, Lock, Moon, ShieldCheck, Sun, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { extractErrorMessage } from '../utils/errorUtils';

export const LoginPage: React.FC = () => {
  const { login, sessionExpired } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(sessionExpired ? 'Сеанс завершен. Выполните вход повторно.' : null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('Введите логин и пароль.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(extractErrorMessage(err, 'Не удалось выполнить вход.'));
    } finally {
      setLoading(false);
    }
  };

  const inputCls = 'w-full pl-10 pr-4 py-2.5 text-[14px] rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] text-[var(--text-main)] placeholder-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/40';

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--bg-app)] relative">
      <div aria-hidden="true" className="pointer-events-none fixed inset-0" style={{
        background: theme === 'dark'
          ? 'radial-gradient(circle at 20% 10%, rgba(70,89,235,0.10), transparent 45%)'
          : 'linear-gradient(180deg, #eef2f9 0%, #f4f6fa 45%, #ffffff 100%)',
      }} />
      <button onClick={toggleTheme} type="button" aria-label="Переключить тему оформления"
        className="absolute top-5 right-5 z-10 px-4 py-2 rounded-full bg-[var(--bg-card)] border border-[var(--border-glass)] flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-main)]">
        {theme === 'dark' ? <Sun className="w-4 h-4 text-[var(--accent-coral)]" /> : <Moon className="w-4 h-4 text-[var(--accent-primary)]" />}
        <span>{theme === 'dark' ? 'Темная тема' : 'Светлая тема'}</span>
      </button>

      <div className="w-full max-w-md z-10">
        <div className="text-center mb-6">
          <h1 className="text-3xl font-medium font-display tracking-tight">Сегментация клиентов</h1>
          <p className="mt-2 text-[14px] text-[var(--text-secondary)]">Кластерный анализ и персонализация программы лояльности</p>
        </div>
        <div className="dusk-card p-7">
          {error && (
            <div role="alert" className="mb-4 p-3.5 rounded-xl bg-[var(--accent-coral-subtle)] text-[var(--accent-coral)] text-[14px] flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="login-username" className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">Логин</label>
              <div className="relative">
                <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
                <input id="login-username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
                  placeholder="Введите логин" className={inputCls} />
              </div>
            </div>
            <div>
              <label htmlFor="login-password" className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">Пароль</label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
                <input id="login-password" type="password" autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} placeholder="Введите пароль" className={inputCls} />
              </div>
            </div>
            <button type="submit" disabled={loading}
              className="w-full mt-2 inline-flex items-center justify-center gap-2 py-2.5 rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] font-medium text-[14px] hover:brightness-105 disabled:opacity-50">
              <span>{loading ? 'Вход...' : 'Войти'}</span>
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>
          <div className="mt-6 pt-5 border-t border-[var(--border-glass)] flex items-start gap-2.5 text-[12px] text-[var(--text-muted)]">
            <ShieldCheck className="w-4 h-4 shrink-0 text-[var(--accent-sage)]" />
            <span>Соединение защищено TLS. После пяти неудачных попыток вход временно блокируется.</span>
          </div>
        </div>
      </div>
    </div>
  );
};
