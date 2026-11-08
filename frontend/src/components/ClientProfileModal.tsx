import React, { useEffect, useState } from 'react';
import { Mail, Phone } from 'lucide-react';
import type { ClientProfile } from '../types';
import { api } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { date, dateTime, money, num } from '../utils/format';
import { Badge, Modal, SegmentBadge, Spinner, TableWrap, Td, Th } from './ui';

const REWARD = (type: string, value: string | number) =>
  type === 'баллы' ? `${num(value)} баллов` : `${type === 'скидка' ? 'Скидка' : 'Кешбэк'} ${num(value, 0)} %`;

export const ClientProfileModal: React.FC<{ clientId: number | null; onClose: () => void }> = ({ clientId, onClose }) => {
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (clientId === null) return;
    setProfile(null);
    setError(null);
    api.get<ClientProfile>(`/api/v1/clients/${clientId}`).then(setProfile).catch((e) => setError(extractErrorMessage(e)));
  }, [clientId]);

  return (
    <Modal open={clientId !== null} onClose={onClose} width="max-w-4xl"
      title={profile ? profile.full_name : 'Профиль клиента'}
      subtitle={profile && <span className="inline-flex items-center gap-2">{profile.external_code} · клиент с {date(profile.created_at)} <SegmentBadge code={profile.segment_code} label={profile.cluster_label} /></span>}>
      {error && <p className="text-[14px] text-[var(--accent-coral)]">{error}</p>}
      {!profile && !error && <Spinner />}
      {profile && (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-4 text-[14px]">
            <span className="inline-flex items-center gap-2"><Phone className="w-4 h-4 text-[var(--accent-primary)]" />{profile.phone}</span>
            <span className="inline-flex items-center gap-2"><Mail className="w-4 h-4 text-[var(--accent-primary)]" />{profile.email || '—'}</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ['Давность покупки', profile.recency_days === null ? '—' : `${num(profile.recency_days, 0)} дн.`],
              ['Проведено чеков', num(profile.frequency)],
              ['Сумма покупок', money(profile.monetary, 0)],
              ['Средний чек', money(profile.avg_check)],
              ['Отменено чеков', num(profile.cancelled_count)],
            ].map(([label, value]) => (
              <div key={label} className="dusk-well px-4 py-3">
                <div className="text-[12px] text-[var(--text-secondary)]">{label}</div>
                <div className="text-[18px] font-medium font-display tabular-nums mt-0.5">{value}</div>
              </div>
            ))}
          </div>
          <div>
            <h3 className="text-[15px] font-medium mb-2">Действующие предложения лояльности</h3>
            {profile.rules.length === 0 ? <p className="text-[14px] text-[var(--text-secondary)]">Активных предложений для клиента нет.</p> : (
              <TableWrap>
                <thead><tr><Th>Правило</Th><Th>Поощрение</Th><Th align="right">Мин. чек</Th><Th align="right">Срок</Th><Th>Основание</Th></tr></thead>
                <tbody>{profile.rules.map((r) => (
                  <tr key={r.id}><Td>{r.rule_name}</Td><Td>{REWARD(r.reward_type, r.reward_value)}</Td><Td align="right">{money(r.min_check_amount, 0)}</Td>
                    <Td align="right">{r.days_valid} дн.</Td><Td><Badge tone={r.source === 'персональное' ? 'accent' : 'neutral'}>{r.source}</Badge></Td></tr>
                ))}</tbody>
              </TableWrap>
            )}
          </div>
          <div>
            <h3 className="text-[15px] font-medium mb-2">История покупок (последние {profile.transactions.length})</h3>
            <TableWrap>
              <thead><tr><Th>Дата</Th><Th align="right">Сумма</Th><Th align="right">Скидка</Th><Th>Статус</Th></tr></thead>
              <tbody>{profile.transactions.map((t) => (
                <tr key={t.id}><Td>{dateTime(t.transaction_date)}</Td><Td align="right">{money(t.total_amount)}</Td><Td align="right">{money(t.discount_amount)}</Td>
                  <Td>{t.status === 'проведен' ? <Badge tone="success">проведен</Badge> : <Badge tone="warning">отменен</Badge>}</Td></tr>
              ))}</tbody>
            </TableWrap>
          </div>
        </div>
      )}
    </Modal>
  );
};
