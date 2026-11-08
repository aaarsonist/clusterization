import React, { useEffect, useState } from 'react';
import { ArrowRight, Download, FileSpreadsheet, Search, Users, X } from 'lucide-react';
import { ClientProfileModal } from '../components/ClientProfileModal';
import { Button, Card, EmptyState, Kpi, SegmentBadge, Spinner, TableWrap, Td, Th } from '../components/ui';
import { useToast } from '../context/ToastContext';
import type { ClientListResponse, Summary } from '../types';
import { api, qs } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { date, money, num } from '../utils/format';

export const ClientsPage: React.FC<{ onOpenSegmentation: () => void }> = ({ onOpenSegmentation }) => {
  const toast = useToast();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [data, setData] = useState<ClientListResponse | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [clusterId, setClusterId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  useEffect(() => { api.get<Summary>('/api/v1/summary').then(setSummary).catch(() => setSummary(null)); }, []);
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 400);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    setData(null);
    api.get<ClientListResponse>(`/api/v1/clients${qs({ page, limit: 10, search: query, cluster_id: clusterId })}`)
      .then(setData).catch((e) => toast.error(extractErrorMessage(e)));
  }, [page, query, clusterId, toast]);

  const exportList = async (format: 'csv' | 'xlsx') => {
    setExporting(format);
    try {
      const name = await api.download(`/api/v1/segmentation/export${qs({ cluster_id: clusterId, format })}`, `mailing.${format}`);
      toast.info(`Сформирован файл ${name}`);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setExporting(null);
    }
  };

  const clusters = summary?.clusters ?? [];
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <Kpi label="Всего клиентов" value={summary ? num(summary.total_clients) : '—'} />
        <Kpi label="Проведенных чеков" value={summary ? num(summary.total_transactions) : '—'} />
        <Kpi label="Выручка" value={summary ? money(summary.total_revenue, 0) : '—'} />
        <Kpi label="Средний чек" value={summary ? money(summary.avg_check) : '—'} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input aria-label="Поиск клиентов" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Поиск по ФИО, коду клиента или номеру телефона"
              className="dusk-input w-full pl-10 pr-4 py-2 text-[14px]" />
          </div>
          <select aria-label="Фильтр по сегменту" className="dusk-input px-4 py-2 text-[14px]" value={clusterId ?? ''} onChange={(e) => { setClusterId(e.target.value ? Number(e.target.value) : null); setPage(1); }}>
            <option value="">Все сегменты</option>
            {clusters.map((c) => <option key={c.id} value={c.id}>{c.cluster_label} ({num(c.client_count)})</option>)}
          </select>
          {(search || clusterId !== null) && <Button variant="ghost" icon={<X className="w-4 h-4" />} onClick={() => { setSearch(''); setClusterId(null); }}>Сбросить</Button>}
          <Button icon={<Download className="w-4 h-4" />} loading={exporting === 'csv'} onClick={() => exportList('csv')}>Выгрузить CSV</Button>
          <Button icon={<FileSpreadsheet className="w-4 h-4" />} loading={exporting === 'xlsx'} onClick={() => exportList('xlsx')}>Выгрузить Excel</Button>
          {summary && !summary.model_algorithm && <Button variant="primary" icon={<ArrowRight className="w-4 h-4" />} onClick={onOpenSegmentation}>К сегментации</Button>}
        </div>
        {!data ? <Spinner /> : data.items.length === 0 ? (
          summary?.total_clients === 0
            ? <EmptyState icon={<Users className="w-5 h-5" />} title="Клиентская база пуста" text="Загрузите транзакционные данные через кнопку «Загрузка данных» в верхней панели." />
            : <EmptyState icon={<Search className="w-5 h-5" />} title="Клиенты с указанными параметрами не найдены" text="Измените условия поиска или сбросьте фильтр." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><Th>Код</Th><Th>Клиент</Th><Th>Телефон</Th><Th>Последняя покупка</Th><Th align="right">Чеков</Th><Th align="right">Сумма покупок</Th><Th>Сегмент</Th></tr></thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.id} onClick={() => setProfileId(c.id)} className="cursor-pointer hover:bg-[var(--bg-input)]" title="Открыть профиль клиента">
                    <Td className="text-[var(--text-secondary)]">{c.external_code}</Td>
                    <Td className="font-medium">{c.full_name}</Td>
                    <Td className="tabular-nums">{c.phone}</Td>
                    <Td>{date(c.last_purchase_date)}</Td>
                    <Td align="right">{num(c.frequency)}</Td>
                    <Td align="right">{money(c.total_spent)}</Td>
                    <Td><SegmentBadge code={c.segment_code} label={c.cluster_label} /></Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <div className="flex items-center justify-between mt-4 text-[13px] text-[var(--text-secondary)]">
              <span>Найдено {num(data.total)} · страница {data.page} из {data.pages}</span>
              <div className="flex gap-2">
                <Button disabled={page <= 1} onClick={() => setPage(page - 1)}>Назад</Button>
                <Button disabled={page >= data.pages} onClick={() => setPage(page + 1)}>Вперед</Button>
              </div>
            </div>
          </>
        )}
      </Card>
      <ClientProfileModal clientId={profileId} onClose={() => setProfileId(null)} />
    </div>
  );
};
