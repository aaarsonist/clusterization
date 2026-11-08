import React, { useMemo, useRef } from 'react';
import { Scatter } from 'react-chartjs-2';
import type { Chart as ChartJS } from 'chart.js';
import { ZoomIn } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import type { ModelClusterProfile, ScatterPoint } from '../types';
import { segmentColor } from '../utils/clusterColors';
import { money, num } from '../utils/format';
import { ChartErrorBoundary } from './ChartErrorBoundary';
import { Button, TableWrap, Td, Th } from './ui';

interface Props {
  points: ScatterPoint[];
  clusters: Pick<ModelClusterProfile, 'cluster_no' | 'segment_code' | 'cluster_label'>[];
  onPointClick?: (clientId: number) => void;
  resetKey?: string | number;
}

// Двумерная проекция клиентов на главные компоненты PCA с масштабированием колесом мыши
export const ScatterPlot: React.FC<Props> = ({ points, clusters, onPointClick, resetKey }) => {
  const { theme } = useTheme();
  const chartRef = useRef<ChartJS<'scatter'> | null>(null);
  const tick = theme === 'dark' ? '#9097a9' : '#586074';
  const grid = theme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';

  const datasets = useMemo(() => clusters.map((c) => {
    const color = segmentColor(c.segment_code, c.cluster_label);
    return {
      label: c.cluster_label,
      data: points.filter((p) => p.cluster_no === c.cluster_no).map((p) => ({ x: p.pca_x, y: p.pca_y, point: p })),
      backgroundColor: `${color}cc`, borderColor: color, pointRadius: 3.5, pointHoverRadius: 6,
    };
  }), [points, clusters]);

  const fallback = (
    <TableWrap>
      <thead><tr><Th>Сегмент</Th><Th align="right">Клиентов на графике</Th></tr></thead>
      <tbody>{datasets.map((d) => <tr key={d.label}><Td>{d.label}</Td><Td align="right">{num(d.data.length)}</Td></tr>)}</tbody>
    </TableWrap>
  );

  return (
    <ChartErrorBoundary title="Ошибка отображения проекции PCA" resetKey={resetKey} fallback={fallback}>
      <div className="relative h-[420px]">
        <Scatter
          ref={chartRef}
          data={{ datasets }}
          options={{
            maintainAspectRatio: false,
            animation: false,
            onClick: (_, elements) => {
              const el = elements[0];
              if (el && onPointClick) {
                const raw = datasets[el.datasetIndex].data[el.index];
                onPointClick(raw.point.client_id);
              }
            },
            plugins: {
              legend: { position: 'bottom', labels: { color: tick, usePointStyle: true, boxWidth: 8 } },
              tooltip: {
                callbacks: {
                  label: (ctx) => {
                    const p = (ctx.raw as { point: ScatterPoint }).point;
                    return [`${p.client_name} (${p.cluster_label})`, `Давность: ${num(p.recency_days, 0)} дн.; чеков: ${num(p.frequency)}; сумма: ${money(p.monetary, 0)}`];
                  },
                },
              },
              zoom: { zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' }, pan: { enabled: true, mode: 'xy' } },
            },
            scales: {
              x: { title: { display: true, text: 'Главная компонента 1', color: tick }, ticks: { color: tick }, grid: { color: grid } },
              y: { title: { display: true, text: 'Главная компонента 2', color: tick }, ticks: { color: tick }, grid: { color: grid } },
            },
          }}
        />
        <Button variant="ghost" className="absolute top-0 right-0" icon={<ZoomIn className="w-4 h-4" />} onClick={() => chartRef.current?.resetZoom()}>Исходный масштаб</Button>
      </div>
    </ChartErrorBoundary>
  );
};
