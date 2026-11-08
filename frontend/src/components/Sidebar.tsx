import React, { useEffect, useState } from 'react';
import { Award, LayoutDashboard, Moon, PanelLeftClose, PanelLeftOpen, PieChart, ShieldCheck, Sun, TrendingUp, Users } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import type { Role } from '../types';

export type NavTab = 'clients' | 'segmentation' | 'loyalty' | 'migration' | 'overview' | 'admin';

export interface NavItem { id: NavTab; label: string; icon: React.ComponentType<{ className?: string }> }

// Состав разделов определяется ролью пользователя (таблица функциональности по ролям)
export const tabsForRole = (role: Role): NavItem[] =>
  role === 'администратор'
    ? [
        { id: 'overview', label: 'Сводка', icon: LayoutDashboard },
        { id: 'admin', label: 'Администрирование', icon: ShieldCheck },
      ]
    : [
        { id: 'clients', label: 'Клиентская база', icon: Users },
        { id: 'segmentation', label: 'Сегментация и анализ', icon: PieChart },
        { id: 'loyalty', label: 'Программа лояльности', icon: Award },
        { id: 'migration', label: 'Миграция клиентов', icon: TrendingUp },
      ];

export const TAB_TITLES: Record<NavTab, string> = {
  clients: 'Клиентская база', segmentation: 'Сегментация и анализ', loyalty: 'Программа лояльности',
  migration: 'Миграция клиентов', overview: 'Сводка', admin: 'Администрирование',
};

export const Sidebar: React.FC<{ tabs: NavItem[]; activeTab: NavTab; onTabChange: (tab: NavTab) => void }> = ({ tabs, activeTab, onTabChange }) => {
  const { theme, toggleTheme } = useTheme();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem('sidebar_collapsed') === 'true'; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem('sidebar_collapsed', String(collapsed)); } catch { /* хранилище недоступно */ }
  }, [collapsed]);

  return (
    <aside className={`${collapsed ? 'w-20' : 'w-72'} shrink-0 dusk-card p-4 flex flex-col justify-between select-none transition-all duration-300`}>
      <div>
        <div className={`pb-4 border-b border-[var(--border-glass)] flex items-center ${collapsed ? 'justify-center' : 'justify-between px-1.5'}`}>
          {!collapsed && (
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent-primary)] shrink-0" aria-hidden="true" />
              <span className="font-display font-medium text-lg truncate">Сегментация клиентов</span>
            </div>
          )}
          <button type="button" onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? 'Развернуть панель навигации' : 'Свернуть панель навигации'}
            title={collapsed ? 'Развернуть панель навигации' : 'Свернуть панель навигации'}
            className="w-9 h-9 rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] flex items-center justify-center text-[var(--text-secondary)] hover:text-[var(--text-main)]">
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>
        <nav className="pt-4 space-y-2" aria-label="Разделы">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button key={id} type="button" onClick={() => onTabChange(id)} title={collapsed ? label : undefined} aria-current={active ? 'page' : undefined}
                className={`w-full flex items-center ${collapsed ? 'justify-center py-3' : 'gap-3 px-3.5 py-3'} rounded-xl text-[15px] font-medium transition-all ${active ? 'bg-[var(--bg-input)] text-[var(--text-main)] border border-[var(--border-glass)]' : 'text-[var(--text-secondary)] hover:text-[var(--text-main)] border border-transparent'}`}>
                <Icon className={`w-5 h-5 shrink-0 ${active ? 'text-[var(--accent-primary)]' : ''}`} />
                {!collapsed && <span className="truncate">{label}</span>}
              </button>
            );
          })}
        </nav>
      </div>
      <button onClick={toggleTheme} type="button" aria-label="Переключить тему оформления"
        className={`w-full flex items-center ${collapsed ? 'justify-center p-2.5' : 'justify-between px-4 py-2.5'} rounded-full bg-[var(--bg-input)] border border-[var(--border-glass)] text-[14px] font-medium text-[var(--text-secondary)]`}>
        {!collapsed && <span>{theme === 'dark' ? 'Темная тема' : 'Светлая тема'}</span>}
        {theme === 'dark' ? <Sun className="w-4 h-4 text-[var(--accent-coral)]" /> : <Moon className="w-4 h-4 text-[var(--accent-primary)]" />}
      </button>
    </aside>
  );
};
