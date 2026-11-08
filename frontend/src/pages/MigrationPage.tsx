import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Camera, Download, FileSpreadsheet, Info, Minus, Search, Sparkles, TrendingUp } from 'lucide-react';
import { CellSelection, MigrationCellModal } from '../components/MigrationCellModal';
import { Button, Card, EmptyState, Kpi, SegmentBadge, Spinner, TableWrap, Tabs, Td, Th } from '../components/ui';
import { useToast } from '../context/ToastContext';
import type { MarketingAlert, MigrationDashboard } from '../types';
import { api, qs } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { date, num, percent } from '../utils/format';

type Filter = 'all' | 'negative' | 'positive';
const ALERT_STYLE: Record<MarketingAlert['type'], { icon: React.ReactNode; cls: string }> = {
  critical: { icon: <AlertTriangle className="w-5 h-5" />, cls: 'text-[var(--accent-coral)] bg-[var(--accent-coral-subtle)]' },
  warning: { icon: <AlertTriangle className="w-5 h-5" />, cls: 'text-[var(--accent-coral)] bg-[var(--accent-coral-subtle)]' },
  success: { icon: <Sparkles className="w-5 h-5" />, cls: 'text-[var(--accent-sage)] bg-[var(--accent-sage-subtle)]' },
  info: { icon: <Info className="w-5 h-5" />, cls: 'text-[var(--accent-primary)] bg-[var(--bg-input)]' },
};

export const MigrationPage: React.FC<{ onCreateRule: (clusterId: number | null) => void; onOpenSegmentation: () => void; onOpenLoyalty: () => void }> = ({ onCreateRule, onOpenSegmentation, onOpenLoyalty }) => {
  const toast = useToast();
  const [data, setData] = useState<MigrationDashboard | null>(null);
  const [fromId, setFromId] = useState<number | null>(null);
  const [toId, setToId] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [cell, setCell] = useState<CellSelection | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');

  const load = useCallback(() => {
    api.get<MigrationDashboard>(`/api/v1/segmentation/migration${qs({ from_snapshot: fromId, to_snapshot: toId })}`)
      .then(setData).catch((e) => toast.error(extractErrorMessage(e)));
  }, [fromId, toId, toast]);
  useEffect(load, [load]);

  const snapshot = async () => {
    setBusy('snapshot');
    try {
      const r = await api.post<{ tracked_clients: number; changed_clients: number }>('/api/v1/segmentation/snapshots');
      toast.success(`Срез T1 зафиксирован: ${num(r.tracked_clients)} клиентов, сменили сегмент ${num(r.changed_clients)}.`);
      setFromId(null);
      setToId(null);
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const exportReport = async (format: 'csv' | 'xlsx') => {
    setBusy(format);
    try {
      const name = await api.download(`/api/v1/segmentation/migration/export${qs({ from_snapshot: data?.from_snapshot?.id, to_snapshot: data?.to_snapshot?.id, format })}`, `migration.${format}`);
      toast.info(`Отчет сформирован: ${name}`);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!data) return <Spinner />;
  if (data.state === 'need_baseline') {
    return <Card><EmptyState icon={<TrendingUp className="w-5 h-5" />} title="Модель сегментации не утверждена" text={data.message}
      action={<Button variant="primary" icon={<ArrowRight className="w-4 h-4" />} onClick={onOpenSegmentation}>Перейти к сегментации</Button>} /></Card>;
  }
  if (data.state === 'need_second_snapshot') {
    return <Card><EmptyState icon={<Camera className="w-5 h-5" />} title="Зафиксирован только срез T0" text={`${data.message} Для демонстрации можно смоделировать прошедший месяц в окне «Загрузка данных».`}
      action={<Button variant="primary" icon={<Camera className="w-4 h-4" />} loading={busy === 'snapshot'} onClick={snapshot}>Зафиксировать срез T1</Button>} /></Card>;
  }

  const { summary, matrix } = data;
  const maxCell = Math.max(1, ...matrix!.matrix.flatMap((row, i) => row.filter((_, j) => j !== i)));
  const label = (s: { id: number; kind: string; reference_date: string; clients: number }) => `${s.kind} · данные на ${date(s.reference_date)} · ${num(s.clients)} клиентов`;
  const sample = data.clients_sample
    .filter((c) => filter === 'all' || c.direction === filter)
    .filter((c) => !search.trim() || `${c.full_name} ${c.external_code} ${c.phone}`.toLowerCase().includes(search.trim().toLowerCase()));

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[13px] text-[var(--text-secondary)]">Начало периода
            <select className="dusk-input block mt-1 px-4 py-2 text-[14px]" value={data.from_snapshot?.id ?? ''} onChange={(e) => setFromId(Number(e.target.value))}>
              {data.snapshots.map((s) => <option key={s.id} value={s.id}>{label(s)}</option>)}
            </select>
          </label>
          <label className="text-[13px] text-[var(--text-secondary)]">Конец периода
            <select className="dusk-input block mt-1 px-4 py-2 text-[14px]" value={data.to_snapshot?.id ?? ''} onChange={(e) => setToId(Number(e.target.value))}>
              {data.snapshots.map((s) => <option key={s.id} value={s.id}>{label(s)}</option>)}
            </select>
          </label>
          <div className="flex-1" />
          <Button icon={<Camera className="w-4 h-4" />} loading={busy === 'snapshot'} onClick={snapshot}>Зафиксировать новый срез</Button>
          <Button icon={<Download className="w-4 h-4" />} loading={busy === 'csv'} onClick={() => exportReport('csv')}>Отчет CSV</Button>
          <Button icon={<FileSpreadsheet className="w-4 h-4" />} loading={busy === 'xlsx'} onClick={() => exportReport('xlsx')}>Отчет Excel</Button>
        </div>
      </Card>

      <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
        <Kpi label="Клиентов сопоставлено" value={num(summary!.total_clients_compared)} />
        <Kpi label="Удержание в сегменте" value={percent(summary!.retention_rate)} hint={`${num(summary!.retained)} клиентов`} tone="success" />
        <Kpi label="Перешли в зону риска" value={num(summary!.churn_risk_count)} tone="warning" />
        <Kpi label="Рост ценности" value={num(summary!.upgrade_count)} tone="success" />
        <Kpi label="Снижение ценности" value={num(summary!.downgrade_count)} />
      </div>

      <div className="space-y-5">
        <Card title="Матрица переходов между сегментами">
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-1 text-[13px]">
              <thead>
                <tr>
                  <th className="text-left font-medium text-[var(--text-muted)] px-2">Было ↓ / Стало →</th>
                  {matrix!.segments.map((s) => <th key={s.cluster_id} className="px-2 py-1 font-medium text-[var(--text-secondary)] text-center">{s.cluster_label}</th>)}
                  <th className="px-2 font-medium text-[var(--text-muted)] text-right">Итого</th>
                </tr>
              </thead>
              <tbody>
                {matrix!.segments.map((from, i) => (
                  <tr key={from.cluster_id}>
                    <th className="text-left px-2 py-1"><SegmentBadge code={from.segment_code} label={from.cluster_label} /></th>
                    {matrix!.matrix[i].map((value, j) => {
                      const to = matrix!.segments[j];
                      const diagonal = i === j;
                      const risk = to.segment_code === 'churn' && !diagonal;
                      const alpha = diagonal ? 0.18 : Math.min(0.85, 0.12 + (value / maxCell) * 0.7);
                      const rgb = diagonal ? '63,159,108' : risk ? '224,112,79' : '91,108,240';
                      return (
                        <td key={to.cluster_id}>
                          <button type="button" disabled={!value} onClick={() => setCell({ from, to, fromSnapshot: data.from_snapshot!.id, toSnapshot: data.to_snapshot!.id })}
                            title={`${from.cluster_label} → ${to.cluster_label}: ${value}`}
                            className="w-full min-w-[64px] py-3 rounded-lg font-medium tabular-nums disabled:cursor-default hover:ring-2 hover:ring-[var(--accent-primary)]"
                            style={{ backgroundColor: value ? `rgba(${rgb},${alpha})` : 'var(--bg-input)' }}>
                            {num(value)}
                          </button>
                        </td>
                      );
                    })}
                    <td className="text-right px-2 tabular-nums text-[var(--text-secondary)]">{num(matrix!.total_from[i])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap gap-4 text-[12px] text-[var(--text-secondary)]">
            <span>Диагональ — клиенты, оставшиеся в сегменте</span>
            <span className="text-[var(--accent-coral)]">Коралловый — переход в зону риска оттока</span>
            <span>Нажмите на ячейку, чтобы открыть список клиентов</span>
          </div>
        </Card>
        <Card title="Маркетинговые сигналы">
          {data.alerts.length === 0 ? <p className="text-[14px] text-[var(--text-secondary)]">Существенных изменений между срезами не выявлено.</p> : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {data.alerts.map((a) => (
                <div key={a.id} className="dusk-well p-4 space-y-2">
                  <div className="flex items-start gap-3">
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${ALERT_STYLE[a.type].cls}`}>{ALERT_STYLE[a.type].icon}</div>
                    <div>
                      <div className="font-medium text-[14px]">{a.title}</div>
                      <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">{a.message}</p>
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-medium tabular-nums">{a.impact}</span>
                    <Button variant="ghost" icon={<ArrowRight className="w-4 h-4" />} onClick={() => (a.target_cluster_id ? onCreateRule(a.target_cluster_id) : onOpenLoyalty())}>{a.action_label}</Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Клиенты, сменившие сегмент" actions={<span className="text-[13px] text-[var(--text-secondary)]">Показаны первые 100 переходов</span>}>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <Tabs value={filter} onChange={setFilter} items={[{ id: 'all', label: 'Все переходы' }, { id: 'negative', label: 'Снижение ценности' }, { id: 'positive', label: 'Рост ценности' }]} />
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input aria-label="Поиск по переходам" className="dusk-input w-full pl-10 pr-4 py-2 text-[14px]" placeholder="Поиск по ФИО, коду или телефону" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        <TableWrap>
          <thead><tr><Th>Клиент</Th><Th>Телефон</Th><Th>Был</Th><Th align="center">Динамика</Th><Th>Стал</Th></tr></thead>
          <tbody>
            {sample.map((c) => (
              <tr key={c.client_id}>
                <Td>{c.full_name} <span className="text-[var(--text-muted)] text-[12px]">{c.external_code}</span></Td>
                <Td className="tabular-nums">{c.phone}</Td>
                <Td>{c.old_segment}</Td>
                <Td align="center">{c.direction === 'positive' ? <ArrowUpRight className="w-4 h-4 inline text-[var(--accent-sage)]" /> : c.direction === 'negative' ? <ArrowDownRight className="w-4 h-4 inline text-[var(--accent-coral)]" /> : <Minus className="w-4 h-4 inline text-[var(--text-muted)]" />}</Td>
                <Td>{c.new_segment}</Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </Card>
      <MigrationCellModal cell={cell} onClose={() => setCell(null)} onCreateRule={(id) => onCreateRule(id)} />
    </div>
  );
};
