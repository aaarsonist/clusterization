import React, { useState } from 'react';
import { Line } from 'react-chartjs-2';
import { useTheme } from '../context/ThemeContext';
import type { XaiData } from '../types';
import { metric, num, percent, plural } from '../utils/format';
import { ChartErrorBoundary } from './ChartErrorBoundary';
import { Modal, Tabs } from './ui';

type Tab = 'kmeans' | 'dbscan' | 'ward';

// Объяснение результатов (XAI): метод локтя и силуэт, график k-NN расстояний, дендрограмма Уорда
export const XaiModal: React.FC<{ open: boolean; onClose: () => void; xai: XaiData }> = ({ open, onClose, xai }) => {
  const { theme } = useTheme();
  const [tab, setTab] = useState<Tab>('kmeans');
  const dark = theme === 'dark';
  const tick = dark ? '#9097a9' : '#586074';
  const grid = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  const blue = dark ? '#8b9bf8' : '#4659eb';
  const coral = dark ? '#f09575' : '#de6e4b';
  const axis = (title: string) => ({ title: { display: true, text: title, color: tick }, ticks: { color: tick }, grid: { color: grid } });
  const explained = xai.explained_variance_ratio.reduce((a, b) => a + b, 0) * 100;

  return (
    <Modal open={open} onClose={onClose} width="max-w-5xl" title="Объяснение результатов кластеризации"
      subtitle={`Две главные компоненты PCA сохраняют ${percent(explained)} дисперсии признаков`}>
      <div className="mb-4">
        <Tabs value={tab} onChange={setTab} items={[
          { id: 'kmeans', label: 'K-Means++: метод локтя и силуэт' }, { id: 'dbscan', label: 'DBSCAN: график k-NN' }, { id: 'ward', label: 'Уорд: дендрограмма' },
        ]} />
      </div>
      {tab === 'kmeans' && (
        <div className="grid lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 h-80">
            <ChartErrorBoundary title="Ошибка графика метода локтя">
              <Line
                data={{
                  labels: xai.elbow_curve.map((p) => p.k),
                  datasets: [
                    { label: 'Внутрикластерная сумма квадратов', data: xai.elbow_curve.map((p) => p.inertia), borderColor: blue, backgroundColor: blue, yAxisID: 'y', tension: 0.25 },
                    { label: 'Коэффициент силуэта', data: xai.elbow_curve.map((p) => p.silhouette), borderColor: coral, backgroundColor: coral, yAxisID: 'y1', tension: 0.25 },
                  ],
                }}
                options={{
                  maintainAspectRatio: false,
                  plugins: { legend: { labels: { color: tick } } },
                  scales: { x: axis('Число кластеров k'), y: axis('Сумма квадратов'), y1: { ...axis('Силуэт'), position: 'right', grid: { display: false } } },
                }}
              />
            </ChartErrorBoundary>
          </div>
          <div className="dusk-well p-5 text-[14px] leading-relaxed text-[var(--text-secondary)]">
            <div className="text-[var(--accent-primary)] font-medium mb-2">Выбрано k = {xai.optimal_k}</div>
            Число кластеров выбирается по максимуму коэффициента силуэта в диапазоне от 3 до 6 с учетом точки перегиба кривой
            внутрикластерной суммы квадратов: дальнейшее увеличение k дает малый выигрыш компактности и дробит устойчивые сегменты.
          </div>
        </div>
      )}
      {tab === 'dbscan' && (
        <div className="grid lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 h-80">
            <ChartErrorBoundary title="Ошибка графика k-NN">
              <Line
                data={{
                  labels: xai.knn_distances.map((p) => p.index),
                  datasets: [
                    { label: `Расстояние до ${xai.min_samples}-го соседа`, data: xai.knn_distances.map((p) => p.distance), borderColor: blue, backgroundColor: `${blue}33`, fill: true, pointRadius: 0, tension: 0.2 },
                    { label: `Радиус ε = ${metric(xai.selected_eps)}`, data: xai.knn_distances.map(() => xai.selected_eps), borderColor: coral, borderDash: [6, 4], pointRadius: 0 },
                  ],
                }}
                options={{ maintainAspectRatio: false, plugins: { legend: { labels: { color: tick } } }, scales: { x: axis('Объекты, упорядоченные по расстоянию'), y: axis('Расстояние') } }}
              />
            </ChartErrorBoundary>
          </div>
          <div className="dusk-well p-5 text-[14px] leading-relaxed text-[var(--text-secondary)]">
            <div className="text-[var(--accent-primary)] font-medium mb-2">ε = {metric(xai.selected_eps)}, minPts = {xai.min_samples}</div>
            Радиус окрестности выбирается по 85-му перцентилю отсортированных расстояний до {xai.min_samples}-го ближайшего соседа.
            Объекты, в окрестности которых меньше {xai.min_samples} точек, относятся к нетипичным клиентам (шуму).
          </div>
        </div>
      )}
      {tab === 'ward' && (
        <div className="grid lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 dusk-well p-3 h-80">
            <Dendrogram xai={xai} line={blue} cut={coral} label={tick} />
          </div>
          <div className="dusk-well p-5 text-[14px] leading-relaxed text-[var(--text-secondary)]">
            <div className="text-[var(--accent-primary)] font-medium mb-2">Высота среза h = {metric(xai.dendrogram.cut_threshold)}</div>
            Метод Уорда последовательно объединяет пары кластеров с наименьшим приростом внутрикластерной суммы квадратов.
            Горизонтальный срез дерева на высоте h дает {num(xai.optimal_k)} {plural(xai.optimal_k, ['кластер', 'кластера', 'кластеров'])}, что согласуется с выбором K-Means++.
          </div>
        </div>
      )}
    </Modal>
  );
};

const Dendrogram: React.FC<{ xai: XaiData; line: string; cut: string; label: string }> = ({ xai, line, cut, label }) => {
  const d = xai.dendrogram;
  const maxX = Math.max(...d.icoord.flat(), 1);
  const maxY = Math.max(...d.dcoord.flat(), d.cut_threshold, 1) * 1.1;
  const sx = (x: number) => (x / maxX) * 960 + 20;
  const sy = (y: number) => 280 - (y / maxY) * 260;
  return (
    <svg viewBox="0 0 1000 300" className="w-full h-full" preserveAspectRatio="none" role="img" aria-label="Дендрограмма иерархической кластеризации">
      {d.icoord.map((xs, i) => (
        <polyline key={i} fill="none" stroke={line} strokeWidth={1.6}
          points={xs.map((x, j) => `${sx(x)},${sy(d.dcoord[i][j])}`).join(' ')} />
      ))}
      <line x1={0} x2={1000} y1={sy(d.cut_threshold)} y2={sy(d.cut_threshold)} stroke={cut} strokeWidth={1.5} strokeDasharray="6 5" />
      <text x={24} y={sy(d.cut_threshold) - 6} fill={cut} fontSize={13}>Срез h = {metric(d.cut_threshold)}</text>
      <text x={24} y={295} fill={label} fontSize={11}>Листья: группы объектов подвыборки (усеченное дерево из 16 узлов)</text>
    </svg>
  );
};
