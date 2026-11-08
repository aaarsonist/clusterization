import React, { useRef, useState } from 'react';
import { CalendarClock, Download, FileUp, RotateCcw, Server } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { api } from '../utils/api';
import { extractErrorMessage } from '../utils/errorUtils';
import { num } from '../utils/format';
import { Badge, Button, Modal, Tabs } from './ui';

type Tab = 'pos' | 'csv' | 'demo';
interface ImportResult { rows_processed: number; transactions_added: number; clients_created: number; errors: string[] }

export const DataSyncModal: React.FC<{ open: boolean; onClose: () => void; onChanged: () => void }> = ({ open, onClose, onChanged }) => {
  const { hasRole } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>('pos');
  const [busy, setBusy] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    try {
      await action();
      onChanged();
    } catch (err) {
      toast.error(extractErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const posSync = () => run('pos', async () => {
    const r = await api.post<{ new_transactions: number; total_transactions: number }>('/api/v1/sync/pos-sync');
    toast.success(`Получено ${num(r.new_transactions)} чеков. Всего в базе: ${num(r.total_transactions)}.`);
  });

  const upload = () => run('csv', async () => {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const r = await api.upload<ImportResult>('/api/v1/sync/upload-csv', form);
    setResult(r);
    toast.success(`Импорт завершен: добавлено ${num(r.transactions_added)} чеков.`);
  });

  const simulate = () => run('month', async () => {
    const r = await api.post<{ new_transactions: number; tracked_clients: number; changed_clients: number }>('/api/v1/sync/demo/simulate-month');
    toast.success(`Смоделирован месяц: ${num(r.new_transactions)} чеков, срез T1 по ${num(r.tracked_clients)} клиентам, сменили сегмент ${num(r.changed_clients)}.`);
  });

  const reset = () => run('reset', async () => {
    const r = await api.post<{ message: string }>('/api/v1/sync/demo/reset-zero-state');
    setConfirmReset(false);
    toast.info(r.message);
  });

  return (
    <Modal open={open} onClose={onClose} title="Загрузка транзакционных данных" subtitle="Источник: кассовый контур и файлы выгрузки" width="max-w-2xl">
      <div className="mb-5">
        <Tabs value={tab} onChange={setTab} items={[
          { id: 'pos', label: 'Обмен с кассами' }, { id: 'csv', label: 'Импорт из файла' }, { id: 'demo', label: 'Демонстрация' },
        ]} />
      </div>

      {tab === 'pos' && (
        <div className="space-y-4">
          <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">
            Регламентный обмен эмулирует закрытие кассовых смен: в базу поступает пакет из 40–80 чеков за последние 7 дней
            (сумма чека 20–350 BYN, около 3 % чеков — отмененные).
          </p>
          <Button variant="primary" icon={<Server className="w-4 h-4" />} loading={busy === 'pos'} onClick={posSync}>Выполнить обмен с кассами</Button>
        </div>
      )}

      {tab === 'csv' && (
        <div className="space-y-4">
          <p className="text-[14px] text-[var(--text-secondary)] leading-relaxed">
            Обязательные колонки: телефон или код клиента, дата и сумма чека. Необязательные: скидка, статус чека, ФИО и e-mail
            (при наличии ФИО новый клиент создается автоматически). Разделитель — точка с запятой или запятая, кодировка UTF-8 или Windows-1251.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button icon={<Download className="w-4 h-4" />} onClick={() => api.download('/api/v1/sync/template-csv', 'pos_transactions_template.csv').catch((e) => toast.error(extractErrorMessage(e)))}>Скачать шаблон</Button>
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} />
            <Button icon={<FileUp className="w-4 h-4" />} onClick={() => fileRef.current?.click()}>{file ? file.name : 'Выбрать файл CSV'}</Button>
            <Button variant="primary" disabled={!file} loading={busy === 'csv'} onClick={upload}>Загрузить и провести</Button>
          </div>
          {result && (
            <div className="dusk-well p-4 text-[14px] space-y-2">
              <div className="flex flex-wrap gap-2">
                <Badge>Строк: {num(result.rows_processed)}</Badge>
                <Badge tone="success">Добавлено чеков: {num(result.transactions_added)}</Badge>
                <Badge tone="accent">Новых клиентов: {num(result.clients_created)}</Badge>
                {result.errors.length > 0 && <Badge tone="warning">Ошибок: {num(result.errors.length)}</Badge>}
              </div>
              {result.errors.length > 0 && <ul className="text-[13px] text-[var(--accent-coral)] space-y-1">{result.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
            </div>
          )}
        </div>
      )}

      {tab === 'demo' && (
        <div className="space-y-5">
          <div className="dusk-well p-4 space-y-3">
            <div className="font-medium">Моделирование прошедшего месяца</div>
            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
              История покупок сдвигается на 30 дней назад, за прошедший месяц генерируются покупки с поведенческим дрейфом сегментов,
              после чего фиксируется срез T1 по центроидам утвержденной модели.
            </p>
            <Button variant="primary" icon={<CalendarClock className="w-4 h-4" />} loading={busy === 'month'} onClick={simulate}>Смоделировать месяц и зафиксировать срез T1</Button>
          </div>
          {hasRole('администратор') && (
            <div className="dusk-well p-4 space-y-3">
              <div className="font-medium">Сброс аналитических данных</div>
              <p className="text-[13px] text-[var(--text-secondary)]">Удаляются модели сегментации, срезы и правила лояльности. Клиенты и чеки сохраняются.</p>
              {confirmReset ? (
                <div className="flex gap-2">
                  <Button variant="danger" loading={busy === 'reset'} onClick={reset}>Подтвердить сброс</Button>
                  <Button onClick={() => setConfirmReset(false)}>Отмена</Button>
                </div>
              ) : (
                <Button icon={<RotateCcw className="w-4 h-4" />} onClick={() => setConfirmReset(true)}>Сбросить аналитические данные</Button>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
};
