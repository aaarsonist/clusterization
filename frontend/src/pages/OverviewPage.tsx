import React, { useEffect, useState } from 'react';
import { Activity, Brain, Database } from 'lucide-react';
import { Bar } from 'react-chartjs-2';
import { Badge, Card, Kpi, Spinner } from '../components/ui';
import { useTheme } from '../context/ThemeContext';
import type { Health, Summary } from '../types';
import { api } from '../utils/api';
import { segmentColor } from '../utils/clusterColors';
import { ALGORITHM_NAMES, dateTime, money, num } from '../utils/format';

const StatusRow: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div className="flex items-center justify-between gap-3 py-3 border-b last:border-0 border-[var(--border-glass)]">
    <div className="flex items-center gap-2.5 text-[14px]">{icon}<span>{label}</span></div>
    <Badge tone={value === 'ok' ? 'success' : 'warning'}>{value === 'ok' ? 'Работает' : value}</Badge>
  </div>
);

export const OverviewPage: React.FC = () => {
  const { theme } = useTheme();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.get<Summary>('/api/v1/summary').then(setSummary).catch(() => setSummary(null));
    fetch('/health').then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
  }, []);

  if (!summary) return <Spinner />;
  const tick = theme === 'dark' ? '#9097a9' : '#586074';
  const grid = theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <Kpi label="Клиентов в базе" value={num(summary.total_clients)} />
        <Kpi label="Проведенных чеков" value={num(summary.total_transactions)} hint={`Отменено: ${num(summary.cancelled_transactions)}`} />
        <Kpi label="Выручка" value={money(summary.total_revenue, 0)} hint={`Скидки: ${money(summary.total_discount, 0)}`} />
        <Kpi label="Средний чек" value={money(summary.avg_check)} hint={`Активных правил лояльности: ${num(summary.active_loyalty_rules)}`} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Card className="xl:col-span-2" title="Распределение клиентов по сегментам" actions={summary.model_algorithm && (
          <Badge tone="accent">{ALGORITHM_NAMES[summary.model_algorithm]} · утверждена {dateTime(summary.model_approved_at)}</Badge>
        )}>
          {summary.clusters.length === 0 ? (
            <p className="text-[14px] text-[var(--text-secondary)] py-8 text-center">Модель сегментации еще не утверждена маркетологом.</p>
          ) : (
            <div className="h-72">
              <Bar
                data={{
                  labels: summary.clusters.map((c) => c.cluster_label),
                  datasets: [{ label: 'Клиентов', data: summary.clusters.map((c) => c.client_count),
                    backgroundColor: summary.clusters.map((c) => segmentColor(c.segment_code, c.cluster_label)), borderRadius: 8 }],
                }}
                options={{ maintainAspectRatio: false, plugins: { legend: { display: false } },
                  scales: { x: { ticks: { color: tick }, grid: { display: false } }, y: { ticks: { color: tick }, grid: { color: grid } } } }}
              />
            </div>
          )}
        </Card>
        <Card title="Состояние системы">
          <StatusRow icon={<Activity className="w-4 h-4 text-[var(--accent-primary)]" />} label="Сервер бизнес-логики" value={health ? 'ok' : 'недоступен'} />
          <StatusRow icon={<Database className="w-4 h-4 text-[var(--accent-primary)]" />} label="СУБД PostgreSQL" value={health?.database ?? 'нет данных'} />
          <StatusRow icon={<Brain className="w-4 h-4 text-[var(--accent-primary)]" />} label="Интеллектуальный сервис" value={health?.ai_service ?? 'нет данных'} />
          <p className="mt-4 text-[12px] text-[var(--text-muted)]">Версия {health?.version ?? '—'} · проверено {dateTime(health?.timestamp)}</p>
        </Card>
      </div>
    </div>
  );
};
