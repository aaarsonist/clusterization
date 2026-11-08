import React, { useEffect, useState } from 'react';
import { Download, FileSpreadsheet, Search, UserMinus, UserPlus } from 'lucide-react';
import { useToast } from '../context/ToastContext';
import type { AudienceResponse, ClientListResponse, LoyaltyRule } from '../types';
import { api, qs } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { money, num } from '../utils/format';
import { Badge, Button, Modal, Spinner, TableWrap, Td, Th } from './ui';

// Аудитория правила лояльности: участники сегмента с учетом ручных включений и исключений (UC-8, UC-9)
export const RuleDetailsModal: React.FC<{ rule: LoyaltyRule | null; onClose: () => void; onChanged: () => void }> = ({ rule, onClose, onChanged }) => {
  const toast = useToast();
  const [audience, setAudience] = useState<AudienceResponse | null>(null);
  const [search, setSearch] = useState('');
  const [candidates, setCandidates] = useState<ClientListResponse | null>(null);
  const [candidateQuery, setCandidateQuery] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = (query = search) => {
    if (!rule) return;
    api.get<AudienceResponse>(`/api/v1/loyalty/rules/${rule.id}/clients${qs({ search: query.trim(), limit: 50 })}`)
      .then(setAudience).catch((e) => toast.error(extractErrorMessage(e)));
  };

  useEffect(() => {
    setAudience(null);
    setSearch('');
    setCandidateQuery('');
    setCandidates(null);
    load('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule?.id]);

  useEffect(() => {
    if (!rule) return;
    const timer = setTimeout(() => load(search), 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    if (candidateQuery.trim().length < 3) { setCandidates(null); return; }
    const timer = setTimeout(() => {
      api.get<ClientListResponse>(`/api/v1/clients${qs({ search: candidateQuery.trim(), limit: 5 })}`).then(setCandidates).catch(() => setCandidates(null));
    }, 350);
    return () => clearTimeout(timer);
  }, [candidateQuery]);

  const act = async (key: string, action: () => Promise<string>) => {
    setBusy(key);
    try {
      toast.success(await action());
      load();
      onChanged();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const exportAudience = async (format: 'csv' | 'xlsx') => {
    if (!rule) return;
    setBusy(format);
    try {
      const name = await api.download(`/api/v1/loyalty/rules/${rule.id}/export${qs({ format })}`, `campaign.${format}`);
      toast.info(`Список клиентов сформирован: ${name}`);
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Modal open={!!rule} onClose={onClose} width="max-w-4xl" title={rule ? `Аудитория правила «${rule.rule_name}»` : ''}
      subtitle={audience && `${audience.cluster_label} · участников: ${num(audience.total_count)} · исключено вручную: ${num(audience.excluded_count)}`}>
      {!audience ? <Spinner /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
              <input aria-label="Поиск в аудитории" className="dusk-input w-full pl-10 pr-4 py-2 text-[14px]" placeholder="Поиск по ФИО, коду или телефону"
                value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <Button icon={<Download className="w-4 h-4" />} loading={busy === 'csv'} onClick={() => exportAudience('csv')}>Выгрузить CSV</Button>
            <Button icon={<FileSpreadsheet className="w-4 h-4" />} loading={busy === 'xlsx'} onClick={() => exportAudience('xlsx')}>Выгрузить Excel</Button>
          </div>

          <div className="dusk-well p-4 space-y-2">
            <div className="text-[13px] font-medium">Добавить клиента вручную</div>
            <input aria-label="Поиск клиента для добавления" className="dusk-input w-full px-4 py-2 text-[14px]" placeholder="Введите не менее трех символов ФИО, кода или телефона"
              value={candidateQuery} onChange={(e) => setCandidateQuery(e.target.value)} />
            {candidates && (candidates.items.length === 0
              ? <p className="text-[13px] text-[var(--text-secondary)]">Клиенты не найдены.</p>
              : candidates.items.map((c) => (
                <div key={c.id} className="flex items-center justify-between gap-3 text-[14px]">
                  <span>{c.full_name} <span className="text-[var(--text-muted)]">· {c.external_code} · {c.cluster_label ?? 'не сегментирован'}</span></span>
                  <Button variant="ghost" icon={<UserPlus className="w-4 h-4" />} loading={busy === `add-${c.id}`}
                    onClick={() => act(`add-${c.id}`, async () => (await api.post<{ message: string }>(`/api/v1/loyalty/rules/${rule!.id}/clients`, { client_id: c.id })).message)}>
                    Добавить
                  </Button>
                </div>
              )))}
          </div>

          <TableWrap>
            <thead><tr><Th>Код</Th><Th>ФИО</Th><Th>Телефон</Th><Th>Сегмент</Th><Th align="right">Сумма покупок</Th><Th align="right">Действие</Th></tr></thead>
            <tbody>
              {audience.clients.length === 0 ? (
                <tr><Td className="text-center text-[var(--text-secondary)]" align="center"><span>Клиенты не найдены</span></Td></tr>
              ) : audience.clients.map((c) => (
                <tr key={c.client_id}>
                  <Td className="text-[var(--text-secondary)]">{c.external_code}</Td>
                  <Td>{c.full_name}{c.is_custom_included && <span className="ml-2"><Badge tone="accent">добавлен вручную</Badge></span>}</Td>
                  <Td className="tabular-nums">{c.phone}</Td>
                  <Td>{c.cluster_label}</Td>
                  <Td align="right">{money(c.total_spent, 0)}</Td>
                  <Td align="right">
                    <Button variant="ghost" icon={<UserMinus className="w-4 h-4" />} loading={busy === `exclude-${c.client_id}`}
                      onClick={() => act(`exclude-${c.client_id}`, async () => (await api.del<{ message: string }>(`/api/v1/loyalty/rules/${rule!.id}/clients/${c.client_id}`)).message)}>
                      Исключить
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <p className="text-[12px] text-[var(--text-muted)]">Показаны первые 50 участников; полный список доступен в выгрузке.</p>
        </div>
      )}
    </Modal>
  );
};
