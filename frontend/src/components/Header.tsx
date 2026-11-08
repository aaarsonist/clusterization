import React, { useCallback, useEffect, useState } from 'react';
import { LogOut, RefreshCw } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import type { SyncStatus } from '../types';
import { api } from '../utils/api';
import { dateTime, num } from '../utils/format';
import { DataSyncModal } from './DataSyncModal';
import { NavTab, TAB_TITLES } from './Sidebar';

export const Header: React.FC<{ activeTab: NavTab; onDataChanged: () => void }> = ({ activeTab, onDataChanged }) => {
  const { user, logout } = useAuth();
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(() => {
    api.get<SyncStatus>('/api/v1/sync/status').then(setStatus).catch(() => setStatus(null));
  }, []);
  useEffect(refresh, [refresh]);

  return (
    <>
      <header className="dusk-card px-6 py-4 flex flex-wrap items-center justify-between gap-4 shrink-0 mb-5">
        <h1 className="text-2xl md:text-[26px] leading-tight font-medium tracking-tight font-display">{TAB_TITLES[activeTab]}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <div className="rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] pl-4 pr-1.5 py-1.5 flex items-center gap-3">
            <span className="w-2 h-2 rounded-full bg-[var(--accent-sage)]" title="Источник данных доступен" />
            <span className="text-[13px] text-[var(--text-secondary)]">Кассовый контур:</span>
            <span className="text-[13px] tabular-nums">
              <span className="font-medium">{status ? num(status.total_transactions) : '—'} чеков</span>
              <span className="text-[var(--text-muted)]"> · </span>
              <span className="text-[var(--text-secondary)]">{dateTime(status?.last_transaction_date)}</span>
            </span>
            <button type="button" onClick={() => setOpen(true)}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] text-[13px] font-medium hover:brightness-105">
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Загрузка данных</span>
            </button>
          </div>
          <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] text-[13px]">
            <div className="w-6 h-6 rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] flex items-center justify-center text-xs font-medium">
              {user?.username.slice(0, 2).toUpperCase()}
            </div>
            <span className="font-medium">{user?.username}</span>
            <span className="text-xs text-[var(--text-secondary)]">{user?.role}</span>
          </div>
          <button onClick={logout} type="button" title="Завершить сеанс"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] text-[13px] font-medium hover:bg-[var(--bg-card-hover)]">
            <LogOut className="w-4 h-4 text-[var(--text-secondary)]" />
            <span>Выйти</span>
          </button>
        </div>
      </header>
      <DataSyncModal open={open} onClose={() => setOpen(false)} onChanged={() => { refresh(); onDataChanged(); }} />
    </>
  );
};
