import React, { useEffect, useState } from 'react';
import { Download, FileSpreadsheet, Plus } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import type { DrillDownResponse, MatrixSegment } from '../types';
import { api, qs } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { money, num } from '../utils/format';
import { Button, Modal, SegmentBadge, Spinner, TableWrap, Td, Th } from './ui';

export interface CellSelection { from: MatrixSegment; to: MatrixSegment; fromSnapshot: number | null; toSnapshot: number | null }

// Детализация ячейки матрицы переходов: состав когорты и ежемесячный оборот, затронутый переходом
export const MigrationCellModal: React.FC<{ cell: CellSelection | null; onClose: () => void; onCreateRule: (clusterId: number) => void }> = ({ cell, onClose, onCreateRule }) => {
  const toast = useToast();
  const [data, setData] = useState<DrillDownResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const params = cell && { from_cluster: cell.from.cluster_id, to_cluster: cell.to.cluster_id, from_snapshot: cell.fromSnapshot, to_snapshot: cell.toSnapshot };

  useEffect(() => {
    if (!cell) return;
    setData(null);
    api.get<DrillDownResponse>(`/api/v1/segmentation/migration/clients${qs(params!)}`).then(setData).catch((e) => toast.error(extractErrorMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cell]);

  const download = async (format: 'csv' | 'xlsx') => {
    setBusy(format);
    try {
      const name = await api.download(`/api/v1/segmentation/migration/clients/export${qs({ ...params!, format })}`, `migration.${format}`);
      toast.info(`Список сформирован: ${name}`);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const impact = Number(data?.total_financial_impact ?? 0);
  return (
    <Modal open={!!cell} onClose={onClose} width="max-w-4xl"
      title={cell ? <span className="inline-flex flex-wrap items-center gap-2"><SegmentBadge code={cell.from.segment_code} label={cell.from.cluster_label} /> → <SegmentBadge code={cell.to.segment_code} label={cell.to.cluster_label} /></span> : ''}
      subtitle={data && `Клиентов: ${num(data.total_clients)} · сумма покупок за период: ${money(data.total_turnover, 0)} · влияние на оборот: ${impact > 0 ? '+' : ''}${money(impact, 0)} в месяц`}
      footer={<>
        <Button icon={<Download className="w-4 h-4" />} loading={busy === 'csv'} onClick={() => download('csv')}>Выгрузить CSV</Button>
        <Button icon={<FileSpreadsheet className="w-4 h-4" />} loading={busy === 'xlsx'} onClick={() => download('xlsx')}>Выгрузить Excel</Button>
        {cell && <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => { onClose(); onCreateRule(cell.to.cluster_id); }}>Создать предложение для сегмента</Button>}
      </>}>
      {!data ? <Spinner label="Загрузка состава когорты..." /> : (
        <TableWrap>
          <thead><tr><Th>Код</Th><Th>ФИО</Th><Th>Телефон</Th><Th align="right">Давность, дн.</Th><Th align="right">Чеков</Th><Th align="right">Сумма покупок</Th><Th align="right">Влияние, BYN/мес.</Th></tr></thead>
          <tbody>
            {data.clients.slice(0, 200).map((c) => (
              <tr key={c.client_id}>
                <Td className="text-[var(--text-secondary)]">{c.external_code}</Td>
                <Td>{c.full_name}</Td>
                <Td className="tabular-nums">{c.phone}</Td>
                <Td align="right">{num(c.recency_days, 0)}</Td>
                <Td align="right">{num(c.frequency)}</Td>
                <Td align="right">{money(c.monetary, 0)}</Td>
                <Td align="right" className={c.impact_type === 'loss' ? 'text-[var(--accent-coral)]' : c.impact_type === 'gain' ? 'text-[var(--accent-sage)]' : ''}>{num(c.financial_impact, 2)}</Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Modal>
  );
};
