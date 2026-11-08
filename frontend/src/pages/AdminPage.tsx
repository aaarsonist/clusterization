import React, { useCallback, useEffect, useState } from 'react';
import { DatabaseBackup, History, KeyRound, Plus, RotateCcw, Save, UserCheck, UserX, Users } from 'lucide-react';
import { Badge, Button, Card, EmptyState, Field, inputClass, Modal, Spinner, TableWrap, Tabs, Td, Th } from '../components/ui';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import type { AuditItem, BackupItem, BackupOverview, Role, UserItem } from '../types';
import { api, qs } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { bytes, dateTime, num } from '../utils/format';

type Tab = 'users' | 'backups' | 'audit';
const PASSWORD_RULE = /^(?=.*[A-Za-zА-Яа-яЁё])(?=.*\d).{8,128}$/;
const LOGIN_RULE = /^[A-Za-z0-9_.-]{3,64}$/;

const UsersTab: React.FC = () => {
  const { user: me } = useAuth();
  const toast = useToast();
  const [users, setUsers] = useState<UserItem[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', role: 'маркетолог' as Role });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [passwordFor, setPasswordFor] = useState<UserItem | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<UserItem[]>('/api/v1/users').then(setUsers).catch((e) => toast.error(extractErrorMessage(e)));
  }, [toast]);
  useEffect(load, [load]);

  const create = async () => {
    const next: Record<string, string> = {};
    if (!LOGIN_RULE.test(form.username)) next.username = 'От 3 до 64 символов: латинские буквы, цифры, точка, дефис, подчеркивание.';
    if (!PASSWORD_RULE.test(form.password)) next.password = 'Не менее 8 символов, хотя бы одна буква и одна цифра.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      await api.post('/api/v1/users', form);
      toast.success(`Пользователь «${form.username}» создан.`);
      setCreating(false);
      setForm({ username: '', password: '', role: 'маркетолог' });
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const update = async (u: UserItem, changes: Partial<Pick<UserItem, 'role' | 'is_active'>>) => {
    try {
      await api.patch(`/api/v1/users/${u.id}`, changes);
      toast.success('Учетная запись обновлена.');
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const savePassword = async () => {
    if (!passwordFor) return;
    if (!PASSWORD_RULE.test(newPassword)) {
      setErrors({ newPassword: 'Не менее 8 символов, хотя бы одна буква и одна цифра.' });
      return;
    }
    setBusy(true);
    try {
      await api.post(`/api/v1/users/${passwordFor.id}/password`, { password: newPassword });
      toast.success(`Пароль пользователя «${passwordFor.username}» изменен.`);
      setPasswordFor(null);
      setNewPassword('');
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  if (!users) return <Spinner />;
  return (
    <Card title="Учетные записи сотрудников" actions={<Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={() => { setErrors({}); setCreating(true); }}>Добавить пользователя</Button>}>
      <TableWrap>
        <thead><tr><Th>Логин</Th><Th>Роль</Th><Th>Статус</Th><Th>Создан</Th><Th>Последний вход</Th><Th align="right">Действия</Th></tr></thead>
        <tbody>
          {users.map((u) => {
            const self = u.id === me?.id;
            return (
              <tr key={u.id}>
                <Td className="font-medium">{u.username}{self && <span className="ml-2 text-[12px] text-[var(--text-muted)]">(вы)</span>}</Td>
                <Td>
                  <select aria-label={`Роль пользователя ${u.username}`} disabled={self} value={u.role} onChange={(e) => update(u, { role: e.target.value as Role })} className="dusk-input px-3 py-1 text-[13px]">
                    <option value="маркетолог">маркетолог</option>
                    <option value="администратор">администратор</option>
                  </select>
                </Td>
                <Td>{u.is_active ? <Badge tone="success">Активен</Badge> : <Badge tone="warning">Деактивирован</Badge>}</Td>
                <Td>{dateTime(u.created_at)}</Td>
                <Td>{dateTime(u.last_login_at)}</Td>
                <Td align="right">
                  <div className="flex justify-end gap-1.5">
                    <Button variant="ghost" icon={<KeyRound className="w-4 h-4" />} onClick={() => { setErrors({}); setNewPassword(''); setPasswordFor(u); }}>Пароль</Button>
                    {!self && (u.is_active
                      ? <Button variant="ghost" icon={<UserX className="w-4 h-4" />} onClick={() => update(u, { is_active: false })}>Деактивировать</Button>
                      : <Button variant="ghost" icon={<UserCheck className="w-4 h-4" />} onClick={() => update(u, { is_active: true })}>Активировать</Button>)}
                  </div>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </TableWrap>

      <Modal open={creating} onClose={() => setCreating(false)} title="Новый пользователь" width="max-w-md"
        footer={<><Button onClick={() => setCreating(false)}>Отмена</Button><Button variant="primary" loading={busy} onClick={create}>Создать</Button></>}>
        <div className="space-y-4">
          <Field label="Логин" error={errors.username}>
            <input className={inputClass(!!errors.username)} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </Field>
          <Field label="Временный пароль" error={errors.password} hint="Не менее 8 символов, буквы и цифры">
            <input type="password" className={inputClass(!!errors.password)} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
          <Field label="Роль">
            <select className={inputClass()} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="маркетолог">Маркетолог</option>
              <option value="администратор">Администратор</option>
            </select>
          </Field>
        </div>
      </Modal>

      <Modal open={!!passwordFor} onClose={() => setPasswordFor(null)} title="Смена пароля" subtitle={passwordFor?.username} width="max-w-md"
        footer={<><Button onClick={() => setPasswordFor(null)}>Отмена</Button><Button variant="primary" loading={busy} onClick={savePassword}>Сохранить</Button></>}>
        <Field label="Новый пароль" error={errors.newPassword}>
          <input type="password" className={inputClass(!!errors.newPassword)} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        </Field>
      </Modal>
    </Card>
  );
};

const BackupsTab: React.FC = () => {
  const toast = useToast();
  const [data, setData] = useState<BackupOverview | null>(null);
  const [settings, setSettings] = useState({ enabled: true, run_hour: 2, retention_count: 14 });
  const [busy, setBusy] = useState<string | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<BackupItem | null>(null);

  const load = useCallback(() => {
    api.get<BackupOverview>('/api/v1/backups').then((d) => {
      setData(d);
      setSettings({ enabled: d.settings.enabled, run_hour: d.settings.run_hour, retention_count: d.settings.retention_count });
    }).catch((e) => toast.error(extractErrorMessage(e)));
  }, [toast]);
  useEffect(load, [load]);

  const act = async (key: string, action: () => Promise<string>) => {
    setBusy(key);
    try {
      toast.success(await action());
      load();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  if (!data) return <Spinner />;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
      <Card title="Автоматическое копирование">
        <div className="space-y-4">
          <label className="flex items-center gap-2.5 text-[14px]">
            <input type="checkbox" checked={settings.enabled} onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })} className="w-4 h-4 accent-[var(--accent-primary)]" />
            Ежедневное резервное копирование
          </label>
          <Field label="Время запуска (Минск)">
            <select className={inputClass()} value={settings.run_hour} onChange={(e) => setSettings({ ...settings, run_hour: Number(e.target.value) })}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
            </select>
          </Field>
          <Field label="Хранить последних копий" hint="От 1 до 90; более старые копии удаляются автоматически">
            <input type="number" min={1} max={90} className={inputClass()} value={settings.retention_count} onChange={(e) => setSettings({ ...settings, retention_count: Number(e.target.value) })} />
          </Field>
          <Button variant="primary" icon={<Save className="w-4 h-4" />} loading={busy === 'settings'}
            onClick={() => act('settings', async () => { await api.put('/api/v1/backups/settings', settings); return 'Параметры резервного копирования сохранены.'; })}>
            Сохранить параметры
          </Button>
          <p className="text-[12px] text-[var(--text-muted)]">Свободно на диске: {bytes(data.free_space_bytes)}. Копии шифруются алгоритмом AES-256-GCM.</p>
        </div>
      </Card>
      <Card className="xl:col-span-2" title="Резервные копии базы данных"
        actions={<Button variant="primary" icon={<DatabaseBackup className="w-4 h-4" />} loading={busy === 'create'}
          onClick={() => act('create', async () => { const b = await api.post<BackupItem>('/api/v1/backups'); return `Создана копия ${b.file_name} (${bytes(b.size_bytes)}).`; })}>
          Создать копию сейчас
        </Button>}>
        {data.backups.length === 0 ? (
          <EmptyState icon={<DatabaseBackup className="w-5 h-5" />} title="Резервных копий пока нет" text="Создайте копию вручную или дождитесь автоматического запуска по расписанию." />
        ) : (
          <TableWrap>
            <thead><tr><Th>Дата создания</Th><Th>Вид</Th><Th align="right">Размер</Th><Th>Автор</Th><Th>Контрольная сумма</Th><Th align="right">Действие</Th></tr></thead>
            <tbody>
              {data.backups.map((b) => (
                <tr key={b.file_name}>
                  <Td>{dateTime(b.created_at)}</Td>
                  <Td><Badge tone={b.kind === 'ручная' ? 'accent' : 'neutral'}>{b.kind}</Badge></Td>
                  <Td align="right">{bytes(b.size_bytes)}</Td>
                  <Td>{b.created_by ?? '—'}</Td>
                  <Td><code className="text-[12px] text-[var(--text-secondary)]">{b.sha256.slice(0, 12)}…</code></Td>
                  <Td align="right"><Button variant="ghost" icon={<RotateCcw className="w-4 h-4" />} onClick={() => setRestoreTarget(b)}>Восстановить</Button></Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>
      <Modal open={!!restoreTarget} onClose={() => setRestoreTarget(null)} title="Восстановление базы данных" width="max-w-lg"
        footer={<>
          <Button onClick={() => setRestoreTarget(null)}>Отмена</Button>
          <Button variant="danger" loading={busy === 'restore'} onClick={() => restoreTarget && act('restore', async () => {
            const r = await api.post<{ message: string }>(`/api/v1/backups/${encodeURIComponent(restoreTarget.file_name)}/restore`);
            setRestoreTarget(null);
            return r.message;
          })}>Восстановить</Button>
        </>}>
        <p className="text-[14px] leading-relaxed">
          Текущее состояние базы данных будет заменено копией от <b>{dateTime(restoreTarget?.created_at)}</b>.
          Перед восстановлением автоматически создается страховочная копия текущего состояния.
        </p>
      </Modal>
    </div>
  );
};

const AuditTab: React.FC = () => {
  const toast = useToast();
  const [items, setItems] = useState<AuditItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [actions, setActions] = useState<string[]>([]);
  const [filters, setFilters] = useState({ action: '', username: '', only_failed: false });
  const [page, setPage] = useState(0);
  const limit = 25;

  useEffect(() => { api.get<string[]>('/api/v1/audit/actions').then(setActions).catch(() => setActions([])); }, []);
  useEffect(() => {
    api.get<{ items: AuditItem[]; total: number }>(`/api/v1/audit${qs({ ...filters, only_failed: filters.only_failed || null, limit, offset: page * limit })}`)
      .then((r) => { setItems(r.items); setTotal(r.total); })
      .catch((e) => toast.error(extractErrorMessage(e)));
  }, [filters, page, toast]);

  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <Card title="Журнал аудита" actions={<span className="text-[13px] text-[var(--text-secondary)]">Событий: {num(total)}</span>}>
      <div className="flex flex-wrap gap-3 mb-4">
        <select aria-label="Тип события" className="dusk-input px-4 py-2 text-[14px]" value={filters.action} onChange={(e) => { setPage(0); setFilters({ ...filters, action: e.target.value }); }}>
          <option value="">Все события</option>
          {actions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <input aria-label="Пользователь" placeholder="Пользователь" className="dusk-input px-4 py-2 text-[14px]" value={filters.username} onChange={(e) => { setPage(0); setFilters({ ...filters, username: e.target.value }); }} />
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={filters.only_failed} onChange={(e) => { setPage(0); setFilters({ ...filters, only_failed: e.target.checked }); }} className="w-4 h-4 accent-[var(--accent-primary)]" />
          Только неуспешные
        </label>
      </div>
      {!items ? <Spinner /> : items.length === 0 ? <EmptyState icon={<History className="w-5 h-5" />} title="События не найдены" /> : (
        <TableWrap>
          <thead><tr><Th>Время</Th><Th>Пользователь</Th><Th>Событие</Th><Th>Объект</Th><Th>Результат</Th><Th>IP-адрес</Th><Th>Подробности</Th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <Td className="whitespace-nowrap">{dateTime(i.event_time)}</Td>
                <Td>{i.username ?? '—'}</Td>
                <Td>{i.action}</Td>
                <Td>{i.object_type ? `${i.object_type} ${i.object_id ?? ''}` : '—'}</Td>
                <Td>{i.success ? <Badge tone="success">успешно</Badge> : <Badge tone="warning">отказ</Badge>}</Td>
                <Td>{i.ip_address ?? '—'}</Td>
                <Td className="text-[12px] text-[var(--text-secondary)] max-w-[280px] truncate">{Object.keys(i.details).length ? JSON.stringify(i.details) : '—'}</Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      <div className="flex items-center justify-between mt-4 text-[13px] text-[var(--text-secondary)]">
        <span>Страница {page + 1} из {pages}</span>
        <div className="flex gap-2">
          <Button disabled={page === 0} onClick={() => setPage(page - 1)}>Назад</Button>
          <Button disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Вперед</Button>
        </div>
      </div>
    </Card>
  );
};

export const AdminPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('users');
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Users className="w-5 h-5 text-[var(--accent-primary)]" />
        <Tabs value={tab} onChange={setTab} items={[
          { id: 'users', label: 'Пользователи' }, { id: 'backups', label: 'Резервное копирование' }, { id: 'audit', label: 'Журнал аудита' },
        ]} />
      </div>
      {tab === 'users' && <UsersTab />}
      {tab === 'backups' && <BackupsTab />}
      {tab === 'audit' && <AuditTab />}
    </div>
  );
};
