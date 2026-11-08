import React, { useCallback, useEffect, useState } from 'react';
import { Award, Calculator, Pencil, Plus, Trash2, Users } from 'lucide-react';
import { RuleDetailsModal } from '../components/RuleDetailsModal';
import { Badge, Button, Card, EmptyState, Field, inputClass, Modal, SegmentBadge, Spinner, TableWrap, Td, Th } from '../components/ui';
import { useToast } from '../context/ToastContext';
import type { ClusterBrief, CurrentSegmentation, DiscountResponse, LoyaltyRule, RewardType, RulePayload } from '../types';
import { api } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { money, num, plural } from '../utils/format';

const EMPTY: RulePayload = { cluster_id: null, rule_name: '', reward_type: 'скидка', reward_value: 10, min_check_amount: 0, days_valid: 30, is_active: true };
const rewardText = (type: RewardType | string, value: string | number) =>
  type === 'баллы' ? `${num(value)} баллов` : `${type === 'скидка' ? 'Скидка' : 'Кешбэк'} ${num(value, Number(value) % 1 ? 1 : 0)} %`;

const validate = (f: RulePayload): Record<string, string> => {
  const e: Record<string, string> = {};
  if (f.rule_name.trim().length < 3) e.rule_name = 'Не менее 3 символов.';
  if (!(f.reward_value > 0)) e.reward_value = 'Значение должно быть больше нуля.';
  else if (f.reward_type !== 'баллы' && f.reward_value > 100) e.reward_value = 'Скидка и кешбэк не могут превышать 100 %.';
  if (f.min_check_amount < 0 || Number.isNaN(f.min_check_amount)) e.min_check_amount = 'Сумма не может быть отрицательной.';
  if (!Number.isInteger(f.days_valid) || f.days_valid <= 0) e.days_valid = 'Целое число дней больше нуля.';
  return e;
};

const PosCalculator: React.FC = () => {
  const toast = useToast();
  const [phone, setPhone] = useState('');
  const [amount, setAmount] = useState('150');
  const [result, setResult] = useState<DiscountResponse | null>(null);
  const [busy, setBusy] = useState(false);

  const calculate = async (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(amount.replace(',', '.'));
    if (!phone.trim() || !(value > 0)) {
      toast.warning('Укажите номер телефона клиента и сумму чека больше нуля.');
      return;
    }
    setBusy(true);
    try {
      setResult(await api.post<DiscountResponse>('/api/v1/loyalty/calculate-discount', { phone: phone.trim(), check_amount: value }));
    } catch (err) {
      setResult(null);
      toast.error(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Расчет выгоды по чеку">
      <form onSubmit={calculate} className="space-y-3">
        <Field label="Телефон клиента" hint="Полный номер или последние 7 цифр">
          <input className={inputClass()} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+375 29 123-45-67" />
        </Field>
        <Field label="Сумма чека, BYN">
          <input className={inputClass()} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Button type="submit" variant="primary" icon={<Calculator className="w-4 h-4" />} loading={busy}>Рассчитать</Button>
      </form>
      {result && (
        <div className="mt-4 dusk-well p-4 space-y-2 text-[14px]">
          <div className="font-medium">{result.client_name} <span className="text-[var(--text-muted)]">· {result.external_code}</span></div>
          <div className="text-[var(--text-secondary)]">Сегмент: {result.cluster_label}</div>
          <div className="text-[var(--text-secondary)]">Правило: {result.applied_rule_name ?? 'не применено'}</div>
          <div className="grid grid-cols-3 gap-2 pt-1">
            <div><div className="text-[12px] text-[var(--text-muted)]">Сумма</div><div className="font-medium">{money(result.original_amount)}</div></div>
            <div><div className="text-[12px] text-[var(--text-muted)]">Скидка</div><div className="font-medium text-[var(--accent-sage)]">{money(result.discount_amount)}</div></div>
            <div><div className="text-[12px] text-[var(--text-muted)]">К оплате</div><div className="font-medium">{money(result.final_amount)}</div></div>
          </div>
          <div className="text-[13px] text-[var(--accent-primary)]">{result.benefit_description}</div>
        </div>
      )}
    </Card>
  );
};

export const LoyaltyPage: React.FC<{ draftClusterId?: number | null; onDraftConsumed: () => void; onOpenSegmentation: () => void }> = ({ draftClusterId, onDraftConsumed, onOpenSegmentation }) => {
  const toast = useToast();
  const [rules, setRules] = useState<LoyaltyRule[] | null>(null);
  const [clusters, setClusters] = useState<ClusterBrief[]>([]);
  const [modelReady, setModelReady] = useState(true);
  const [editing, setEditing] = useState<LoyaltyRule | 'new' | null>(null);
  const [form, setForm] = useState<RulePayload>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [audienceRule, setAudienceRule] = useState<LoyaltyRule | null>(null);
  const [deleting, setDeleting] = useState<LoyaltyRule | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<LoyaltyRule[]>('/api/v1/loyalty/rules').then(setRules).catch((e) => toast.error(extractErrorMessage(e)));
  }, [toast]);

  useEffect(() => {
    load();
    api.get<CurrentSegmentation>('/api/v1/segmentation/current').then((c) => { setClusters(c.clusters); setModelReady(c.is_initialized); }).catch(() => setClusters([]));
  }, [load]);

  const openForm = (rule: LoyaltyRule | 'new', clusterId: number | null = null) => {
    setErrors({});
    setForm(rule === 'new' ? { ...EMPTY, cluster_id: clusterId } : {
      cluster_id: rule.cluster_id, rule_name: rule.rule_name, reward_type: rule.reward_type, reward_value: Number(rule.reward_value),
      min_check_amount: Number(rule.min_check_amount), days_valid: rule.days_valid, is_active: rule.is_active,
    });
    setEditing(rule);
  };

  useEffect(() => {
    if (draftClusterId !== undefined) {
      openForm('new', draftClusterId);
      onDraftConsumed();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftClusterId]);

  const save = async () => {
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      if (editing === 'new') {
        await api.post('/api/v1/loyalty/rules', { ...form, rule_name: form.rule_name.trim() });
        toast.success('Правило лояльности создано и активировано.');
      } else if (editing) {
        await api.put(`/api/v1/loyalty/rules/${editing.id}`, { ...form, rule_name: form.rule_name.trim() });
        toast.success('Изменения правила сохранены.');
      }
      setEditing(null);
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (rule: LoyaltyRule) => {
    try {
      await api.put(`/api/v1/loyalty/rules/${rule.id}`, { is_active: !rule.is_active });
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const remove = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.del(`/api/v1/loyalty/rules/${deleting.id}`);
      toast.info(`Правило «${deleting.rule_name}» удалено.`);
      setDeleting(null);
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const set = <K extends keyof RulePayload>(key: K, value: RulePayload[K]) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
      <Card className="xl:col-span-2" title="Правила персонализированной лояльности"
        actions={<Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => openForm('new')}>Создать правило</Button>}>
        {!modelReady && (
          <div className="mb-4 p-3.5 rounded-xl bg-[var(--accent-coral-subtle)] text-[14px] flex flex-wrap items-center justify-between gap-2">
            <span>Модель сегментации не утверждена: доступны только общие правила для всех клиентов.</span>
            <Button onClick={onOpenSegmentation}>Перейти к сегментации</Button>
          </div>
        )}
        {!rules ? <Spinner /> : rules.length === 0 ? (
          <EmptyState icon={<Award className="w-5 h-5" />} title="Правил пока нет" text="Создайте первое персональное предложение для сегмента клиентов." />
        ) : (
          <TableWrap>
            <thead><tr><Th>Сегмент</Th><Th>Правило</Th><Th>Поощрение</Th><Th align="right">Мин. чек</Th><Th align="right">Срок</Th><Th align="right">Аудитория</Th><Th align="center">Активно</Th><Th align="right">Действия</Th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className={r.is_active ? '' : 'opacity-60'}>
                  <Td><SegmentBadge code={r.segment_code} label={r.cluster_label} /></Td>
                  <Td className="font-medium">{r.rule_name}</Td>
                  <Td>{rewardText(r.reward_type, r.reward_value)}</Td>
                  <Td align="right">{money(r.min_check_amount, 0)}</Td>
                  <Td align="right">{r.days_valid} дн.</Td>
                  <Td align="right">{num(r.audience_count)}</Td>
                  <Td align="center">
                    <button type="button" role="switch" aria-checked={r.is_active} aria-label={`Активность правила ${r.rule_name}`} onClick={() => toggle(r)}
                      className={`w-10 h-6 rounded-full relative transition-colors ${r.is_active ? 'bg-[var(--accent-sage)]' : 'bg-[var(--text-muted)]'}`}>
                      <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all ${r.is_active ? 'left-5' : 'left-1'}`} />
                    </button>
                  </Td>
                  <Td align="right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" title="Аудитория правила" icon={<Users className="w-4 h-4" />} onClick={() => setAudienceRule(r)}>Аудитория</Button>
                      <Button variant="ghost" title="Редактировать" aria-label="Редактировать" icon={<Pencil className="w-4 h-4" />} onClick={() => openForm(r)} />
                      <Button variant="ghost" title="Удалить" aria-label="Удалить" icon={<Trash2 className="w-4 h-4" />} onClick={() => setDeleting(r)} />
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>
      <PosCalculator />

      <Modal open={editing !== null} onClose={() => setEditing(null)} width="max-w-lg" title={editing === 'new' ? 'Новое правило лояльности' : 'Редактирование правила'}
        footer={<><Button onClick={() => setEditing(null)}>Отмена</Button><Button variant="primary" loading={busy} onClick={save}>{editing === 'new' ? 'Активировать правило' : 'Сохранить'}</Button></>}>
        <div className="space-y-4">
          <Field label="Наименование предложения" error={errors.rule_name}>
            <input className={inputClass(!!errors.rule_name)} value={form.rule_name} onChange={(e) => set('rule_name', e.target.value)} placeholder="Например: скидка 10 % на повторную покупку" />
          </Field>
          <Field label="Целевой сегмент">
            <select className={inputClass()} value={form.cluster_id ?? ''} onChange={(e) => set('cluster_id', e.target.value ? Number(e.target.value) : null)}>
              <option value="">Все клиенты (общее правило)</option>
              {clusters.map((c) => <option key={c.id} value={c.id}>{c.cluster_label} ({num(c.client_count)} {plural(c.client_count, ['клиент', 'клиента', 'клиентов'])})</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Тип поощрения">
              <select className={inputClass()} value={form.reward_type} onChange={(e) => set('reward_type', e.target.value as RewardType)}>
                <option value="скидка">Скидка, %</option>
                <option value="кешбэк">Кешбэк, %</option>
                <option value="баллы">Бонусные баллы</option>
              </select>
            </Field>
            <Field label={form.reward_type === 'баллы' ? 'Количество баллов' : 'Размер, %'} error={errors.reward_value}>
              <input type="number" step="0.01" className={inputClass(!!errors.reward_value)} value={form.reward_value} onChange={(e) => set('reward_value', Number(e.target.value))} />
            </Field>
            <Field label="Минимальная сумма чека, BYN" error={errors.min_check_amount}>
              <input type="number" step="0.01" className={inputClass(!!errors.min_check_amount)} value={form.min_check_amount} onChange={(e) => set('min_check_amount', Number(e.target.value))} />
            </Field>
            <Field label="Срок действия, дней" error={errors.days_valid}>
              <input type="number" className={inputClass(!!errors.days_valid)} value={form.days_valid} onChange={(e) => set('days_valid', Number(e.target.value))} />
            </Field>
          </div>
          <label className="flex items-center gap-2.5 text-[14px]">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} className="w-4 h-4 accent-[var(--accent-primary)]" />
            Правило активно
          </label>
        </div>
      </Modal>

      <Modal open={!!deleting} onClose={() => setDeleting(null)} width="max-w-md" title="Удаление правила"
        footer={<><Button onClick={() => setDeleting(null)}>Отмена</Button><Button variant="danger" loading={busy} onClick={remove}>Удалить</Button></>}>
        <p className="text-[14px]">Удалить правило «{deleting?.rule_name}»? Ручные включения и исключения клиентов будут удалены вместе с ним.</p>
        {deleting && <div className="mt-3"><Badge>{rewardText(deleting.reward_type, deleting.reward_value)}</Badge></div>}
      </Modal>

      <RuleDetailsModal rule={audienceRule} onClose={() => setAudienceRule(null)} onChanged={load} />
    </div>
  );
};
