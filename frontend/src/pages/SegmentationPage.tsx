import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, BrainCircuit, CheckCircle2, Download, FileSpreadsheet, Lightbulb, Loader2, Play, Plus, Sparkles, Table2 } from 'lucide-react';
import { ClientProfileModal } from '../components/ClientProfileModal';
import { ScatterPlot } from '../components/ScatterPlot';
import { Badge, Button, Card, EmptyState, Modal, Spinner, TableWrap, Td, Th } from '../components/ui';
import { XaiModal } from '../components/XaiModal';
import { useToast } from '../context/ToastContext';
import type { AlgorithmId, ClusterBrief, CurrentSegmentation, ModelClusterProfile, ModelSummary, PointsResponse, RunDetail } from '../types';
import { api, qs } from '../utils/api';
import { segmentColor } from '../utils/clusterColors';
import { extractErrorMessage } from '../utils/errorUtils';
import { ALGORITHM_NAMES, dateTime, metric, money, num, percent } from '../utils/format';

const PERIODS = [{ days: 30, label: '1 месяц' }, { days: 90, label: '3 месяца' }, { days: 180, label: '6 месяцев' }, { days: 365, label: '1 год' }];
const STATUS_TEXT: Record<string, { text: string; tone: 'neutral' | 'success' | 'warning' | 'accent' }> = {
  'черновик': { text: 'Матрица признаков сформирована', tone: 'neutral' },
  'расчет': { text: 'Идет расчет моделей', tone: 'accent' },
  'рассчитан': { text: 'Модели рассчитаны', tone: 'success' },
  'ошибка': { text: 'Ошибка расчета', tone: 'warning' },
};

const ClusterCard: React.FC<{ c: ModelClusterProfile | ClusterBrief; actions?: React.ReactNode }> = ({ c, actions }) => {
  const color = segmentColor(c.segment_code, c.cluster_label);
  const silhouette = 'silhouette' in c ? c.silhouette : c.silhouette_score;
  return (
    <div className="dusk-well p-4 flex flex-col gap-2" style={{ borderTop: `3px solid ${color}` }}>
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium font-display" style={{ color }}>{c.cluster_label}</div>
        <Badge>{percent(c.size_percent)}</Badge>
      </div>
      <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed flex-1">{c.description}</p>
      <div className="grid grid-cols-3 gap-2 text-[12px]">
        <div><div className="text-[var(--text-muted)]">Давность</div><div className="font-medium tabular-nums">{num(c.r_center, 0)} дн.</div></div>
        <div><div className="text-[var(--text-muted)]">Чеков</div><div className="font-medium tabular-nums">{num(c.f_center, 1)}</div></div>
        <div><div className="text-[var(--text-muted)]">Сумма</div><div className="font-medium tabular-nums">{money(c.m_center, 0)}</div></div>
      </div>
      <div className="flex items-center justify-between text-[12px] text-[var(--text-secondary)]">
        <span>{num(c.client_count)} клиентов</span>
        <span>Силуэт: {metric(silhouette)}</span>
      </div>
      {actions && <div className="flex flex-wrap gap-1.5 pt-1">{actions}</div>}
    </div>
  );
};

export const SegmentationPage: React.FC<{ onCreateRule: (clusterId: number | null) => void }> = ({ onCreateRule }) => {
  const toast = useToast();
  const [current, setCurrent] = useState<CurrentSegmentation | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [days, setDays] = useState(365);
  const [targetK, setTargetK] = useState<number | null>(null);
  const [selected, setSelected] = useState<AlgorithmId>('kmeans');
  const [points, setPoints] = useState<PointsResponse | null>(null);
  const [approvedPoints, setApprovedPoints] = useState<PointsResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [xaiOpen, setXaiOpen] = useState(false);
  const [confirmApprove, setConfirmApprove] = useState(false);
  const [profileId, setProfileId] = useState<number | null>(null);
  const winnerApplied = useRef<number | null>(null);

  const loadCurrent = useCallback(async () => {
    try {
      const c = await api.get<CurrentSegmentation>('/api/v1/segmentation/current');
      setCurrent(c);
      if (c.run && c.run.algorithm) {
        api.get<PointsResponse>(`/api/v1/segmentation/runs/${c.run.id}/points${qs({ algorithm: c.run.algorithm })}`).then(setApprovedPoints).catch(() => setApprovedPoints(null));
      } else {
        setApprovedPoints(null);
      }
      if (c.latest_run) {
        const r = await api.get<RunDetail>(`/api/v1/segmentation/runs/${c.latest_run.id}`);
        setRun(r);
        setDays(r.days_period);
      } else {
        setRun(null);
      }
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  }, [toast]);
  useEffect(() => { loadCurrent(); }, [loadCurrent]);

  // Опрос состояния фонового расчета (паттерн асинхронного запроса-ответа)
  useEffect(() => {
    if (run?.status !== 'расчет') return;
    const timer = setInterval(async () => {
      try {
        const next = await api.get<RunDetail>(`/api/v1/segmentation/runs/${run.id}`);
        if (next.status !== 'расчет') {
          setRun(next);
          if (next.status === 'ошибка') toast.error(next.error_message || 'Ошибка расчета моделей');
          else toast.success('Сравнение моделей завершено.');
        }
      } catch { /* повтор на следующем шаге опроса */ }
    }, 1500);
    return () => clearInterval(timer);
  }, [run?.status, run?.id, toast]);

  useEffect(() => {
    if (run?.status === 'рассчитан' && run.xai && winnerApplied.current !== run.id) {
      winnerApplied.current = run.id;
      setSelected(run.xai.winner.algorithm_id);
    }
  }, [run]);

  useEffect(() => {
    if (run?.status !== 'рассчитан') { setPoints(null); return; }
    setPoints(null);
    api.get<PointsResponse>(`/api/v1/segmentation/runs/${run.id}/points${qs({ algorithm: selected })}`).then(setPoints).catch((e) => toast.error(extractErrorMessage(e)));
  }, [run?.id, run?.status, selected, toast]);

  const act = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    try { await action(); } catch (e) { toast.error(extractErrorMessage(e)); } finally { setBusy(null); }
  };

  const createRun = () => act('matrix', async () => {
    const r = await api.post<RunDetail>('/api/v1/segmentation/runs', { days_period: days });
    setRun(r);
    toast.success(`Матрица признаков сформирована: ${num(r.features.clients)} клиентов.`);
  });
  const startBenchmark = () => act('bench', async () => {
    if (!run) return;
    setRun(await api.post<RunDetail>(`/api/v1/segmentation/runs/${run.id}/benchmark`, { target_k: targetK }));
  });
  const approve = () => act('approve', async () => {
    if (!run) return;
    const r = await api.post<{ clusters_count: number; assigned_clients: number; relinked_rules: number }>(`/api/v1/segmentation/runs/${run.id}/approve`, { algorithm: selected });
    setConfirmApprove(false);
    toast.success(`Модель ${ALGORITHM_NAMES[selected]} утверждена: ${num(r.clusters_count)} сегментов, ${num(r.assigned_clients)} клиентов. Срез T0 зафиксирован.`);
    await loadCurrent();
  });
  const exportSegment = (clusterId: number, format: 'csv' | 'xlsx') => act(`export-${clusterId}-${format}`, async () => {
    const name = await api.download(`/api/v1/segmentation/export${qs({ cluster_id: clusterId, format })}`, `mailing.${format}`);
    toast.info(`Список рассылки сформирован: ${name}`);
  });

  if (!current) return <Spinner />;
  const models: ModelSummary[] = run?.metrics?.models ?? [];
  const model = models.find((m) => m.algorithm_id === selected);
  const winner = run?.xai?.winner;

  return (
    <div className="space-y-5">
      {current.is_initialized && current.run && (
        <Card title="Утвержденная модель сегментации" actions={<>
          <Badge tone="accent">{ALGORITHM_NAMES[current.run.algorithm!]}</Badge>
          <Badge>Утверждена {dateTime(current.run.approved_at)}</Badge>
          <Badge>Период {num(current.run.days_period)} дн.</Badge>
          <Badge tone="success">Силуэт {metric(current.silhouette_score)}</Badge>
          <Badge>Индекс Дэвиса–Болдина {metric(current.davies_bouldin_score)}</Badge>
        </>}>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">
            {current.clusters.map((c) => (
              <ClusterCard key={c.id} c={c} actions={<>
                <Button variant="ghost" icon={<Download className="w-3.5 h-3.5" />} loading={busy === `export-${c.id}-csv`} onClick={() => exportSegment(c.id, 'csv')}>CSV</Button>
                <Button variant="ghost" icon={<FileSpreadsheet className="w-3.5 h-3.5" />} loading={busy === `export-${c.id}-xlsx`} onClick={() => exportSegment(c.id, 'xlsx')}>Excel</Button>
                <Button variant="ghost" icon={<Plus className="w-3.5 h-3.5" />} onClick={() => onCreateRule(c.id)}>Правило</Button>
              </>} />
            ))}
          </div>
          {approvedPoints ? (
            <>
              <ScatterPlot points={approvedPoints.points} resetKey={current.run.id}
                clusters={current.clusters.map((c) => ({ cluster_no: c.cluster_no, segment_code: c.segment_code, cluster_label: c.cluster_label }))}
                onPointClick={setProfileId} />
              <p className="mt-2 text-[12px] text-[var(--text-muted)]">
                Показано {num(approvedPoints.shown)} из {num(approvedPoints.total)} клиентов по состоянию на момент утверждения. Нажмите на точку, чтобы открыть профиль клиента; колесо мыши — масштабирование.
              </p>
            </>
          ) : <Spinner />}
        </Card>
      )}

      <Card title={current.is_initialized ? 'Новый анализ клиентской базы' : 'Кластерный анализ клиентской базы'}>
        {!current.is_initialized && !run && (
          <EmptyState icon={<BrainCircuit className="w-5 h-5" />} title="Модель сегментации еще не утверждена"
            text="Сформируйте матрицу признаков за выбранный период, сравните три алгоритма кластеризации и утвердите лучшую модель." />
        )}
        <div className="grid lg:grid-cols-2 gap-5">
          <div className="dusk-well p-5 space-y-4">
            <div className="flex items-center gap-2 font-medium"><span className="w-6 h-6 rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] text-[12px] flex items-center justify-center">1</span>Матрица признаков RFM</div>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Период анализа">
              {PERIODS.map((p) => (
                <button key={p.days} type="button" onClick={() => setDays(p.days)}
                  className={`px-4 py-1.5 rounded-full text-[13px] font-medium border ${days === p.days ? 'bg-[var(--accent-primary)] text-[var(--accent-primary-text)] border-transparent' : 'border-[var(--border-glass)] text-[var(--text-secondary)]'}`}>
                  {p.label}
                </button>
              ))}
            </div>
            <Button variant="primary" icon={<Table2 className="w-4 h-4" />} loading={busy === 'matrix'} disabled={run?.status === 'расчет'} onClick={createRun}>Сформировать матрицу признаков</Button>
            {run && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <Badge tone={STATUS_TEXT[run.status]?.tone ?? 'neutral'}>{STATUS_TEXT[run.status]?.text ?? run.status}</Badge>
                  <span className="text-[var(--text-secondary)]">Прогон № {run.id} · период {num(run.days_period)} дн.</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-[13px]">
                  <div className="dusk-card px-3 py-2"><div className="text-[var(--text-muted)] text-[12px]">Клиентов</div><div className="font-medium">{num(run.features.clients)}</div><div className="text-[12px] text-[var(--text-secondary)]">активных {num(run.features.active_clients)}</div></div>
                  <div className="dusk-card px-3 py-2"><div className="text-[var(--text-muted)] text-[12px]">Давность, дн.</div><div className="font-medium">{num(run.features.recency_mean, 1)}</div><div className="text-[12px] text-[var(--text-secondary)]">медиана {num(run.features.recency_median, 0)}</div></div>
                  <div className="dusk-card px-3 py-2"><div className="text-[var(--text-muted)] text-[12px]">Чеков / сумма</div><div className="font-medium">{num(run.features.frequency_mean, 1)} / {money(run.features.monetary_mean, 0)}</div><div className="text-[12px] text-[var(--text-secondary)]">средние значения</div></div>
                </div>
              </div>
            )}
          </div>
          <div className="dusk-well p-5 space-y-4">
            <div className="flex items-center gap-2 font-medium"><span className="w-6 h-6 rounded-full bg-[var(--accent-primary)] text-[var(--accent-primary-text)] text-[12px] flex items-center justify-center">2</span>Сравнение моделей кластеризации</div>
            <label className="flex items-center gap-3 text-[14px]">
              <span className="text-[var(--text-secondary)]">Число кластеров:</span>
              <select aria-label="Число кластеров" className="dusk-input px-4 py-1.5 text-[14px]" value={targetK ?? ''} onChange={(e) => setTargetK(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Автоподбор</option>
                {[2, 3, 4, 5, 6, 7, 8].map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed">
              Интеллектуальный сервис обучает K-Means++, иерархическую модель Уорда и DBSCAN, рассчитывает силуэт и индекс Дэвиса–Болдина и рекомендует лучшую модель.
            </p>
            <Button variant="primary" icon={<Play className="w-4 h-4" />} loading={busy === 'bench'}
              disabled={!run || run.status === 'расчет'} onClick={startBenchmark}>Запустить сравнение моделей</Button>
            {run?.status === 'расчет' && <div className="flex items-center gap-2 text-[14px] text-[var(--accent-primary)]"><Loader2 className="w-4 h-4 animate-spin" />Идет расчет в интеллектуальном сервисе...</div>}
            {run?.status === 'ошибка' && <div className="flex items-start gap-2 text-[14px] text-[var(--accent-coral)]"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />{run.error_message}</div>}
          </div>
        </div>
      </Card>

      {run?.status === 'рассчитан' && winner && model && (
        <>
          <Card title="Результаты сравнения моделей" actions={<>
            <Button icon={<Lightbulb className="w-4 h-4" />} onClick={() => setXaiOpen(true)}>Объяснение результатов</Button>
            <Button variant="primary" icon={<CheckCircle2 className="w-4 h-4" />} onClick={() => setConfirmApprove(true)}>Утвердить модель {ALGORITHM_NAMES[selected]}</Button>
          </>}>
            <div className={`rounded-xl p-4 mb-4 flex gap-3 ${winner.low_quality ? 'bg-[var(--accent-coral-subtle)]' : 'bg-[var(--accent-sage-subtle)]'}`}>
              {winner.low_quality ? <AlertTriangle className="w-5 h-5 shrink-0 text-[var(--accent-coral)]" /> : <Sparkles className="w-5 h-5 shrink-0 text-[var(--accent-sage)]" />}
              <div className="text-[14px] leading-relaxed space-y-1">
                <div className="font-medium">Рекомендуемая модель: {winner.model_name}</div>
                <div>{winner.verdict} {winner.justification}</div>
                <div className={winner.low_quality ? 'text-[var(--accent-coral)] font-medium' : 'text-[var(--text-secondary)]'}>{winner.recommendation}</div>
              </div>
            </div>
            <TableWrap>
              <thead><tr><Th>Модель</Th><Th align="right">Силуэт</Th><Th align="right">Индекс Дэвиса–Болдина</Th><Th align="center">Кластеров</Th><Th align="right">Шум</Th><Th align="right">Интегральная оценка</Th><Th>Применимость</Th></tr></thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.algorithm_id} onClick={() => setSelected(m.algorithm_id)} className={`cursor-pointer ${selected === m.algorithm_id ? 'bg-[var(--bg-input)]' : 'hover:bg-[var(--bg-input)]'}`}>
                    <Td className="font-medium">
                      <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input type="radio" name="model" checked={selected === m.algorithm_id} onChange={() => setSelected(m.algorithm_id)} className="accent-[var(--accent-primary)]" />
                        {m.name}{m.is_winner && <Badge tone="success">рекомендована</Badge>}
                      </label>
                    </Td>
                    <Td align="right">{metric(m.silhouette_score)}</Td>
                    <Td align="right">{metric(m.davies_bouldin_score)}</Td>
                    <Td align="center">{m.cluster_count}</Td>
                    <Td align="right">{percent(m.noise_percent)}</Td>
                    <Td align="right">{metric(m.score)}</Td>
                    <Td><Badge tone={m.business_suitability === 'Высокая' ? 'success' : m.business_suitability === 'Умеренная' ? 'neutral' : 'warning'}>{m.suitability_badge}</Badge></Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <p className="mt-2 text-[12px] text-[var(--text-muted)]">
              Расчет по {num(run.metrics?.n_samples)} клиентам занял {num((run.metrics?.duration_ms ?? 0) / 1000, 2)} с. Интегральная оценка: силуэт − 0,15 × min(3; индекс Дэвиса–Болдина) − штрафы за шум.
            </p>
          </Card>
          <Card title={`Сегменты модели «${model.name}»`}>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-5">
              {model.clusters.map((c) => <ClusterCard key={c.cluster_no} c={c} />)}
            </div>
            {points ? (
              <>
                <ScatterPlot points={points.points} clusters={model.clusters} onPointClick={setProfileId} resetKey={`${run.id}-${selected}`} />
                <p className="mt-2 text-[12px] text-[var(--text-muted)]">Показано {num(points.shown)} из {num(points.total)} клиентов. Скрыть сегмент можно щелчком по легенде.</p>
              </>
            ) : <Spinner />}
          </Card>
          {run.xai && <XaiModal open={xaiOpen} onClose={() => setXaiOpen(false)} xai={run.xai} />}
          <Modal open={confirmApprove} onClose={() => setConfirmApprove(false)} title="Утверждение модели сегментации" width="max-w-lg"
            footer={<><Button onClick={() => setConfirmApprove(false)}>Отмена</Button><Button variant="primary" loading={busy === 'approve'} onClick={approve}>Утвердить</Button></>}>
            <div className="space-y-3 text-[14px] leading-relaxed">
              <p>Будет утверждена модель <b>{model.name}</b> ({model.cluster_count} сегментов, силуэт {metric(model.silhouette_score)}). Клиенты получат сегменты, будет зафиксирован срез T0.</p>
              {current.is_initialized && <p className="text-[var(--text-secondary)]">Текущая утвержденная модель будет перенесена в архив, действующие правила лояльности будут перепривязаны к сегментам новой модели.</p>}
              {winner.low_quality && <p className="text-[var(--accent-coral)]">Внимание: качество разбиения ниже порога {metric(winner.quality_threshold, 2)}.</p>}
              {selected !== winner.algorithm_id && <p className="text-[var(--accent-coral)]">Выбранная модель отличается от рекомендованной интеллектуальным сервисом.</p>}
            </div>
          </Modal>
        </>
      )}
      <ClientProfileModal clientId={profileId} onClose={() => setProfileId(null)} />
    </div>
  );
};
