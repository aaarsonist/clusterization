import type { SegmentCode } from '../types';

// Устойчивые цвета сегментов по их бизнес-коду (одинаковы во всех разделах интерфейса)
export const SEGMENT_COLORS: Record<SegmentCode, string> = {
  vip: '#5b6cf0',
  churn: '#e0704f',
  newbie: '#9a7ef0',
  bargain: '#3f9f6c',
  regular: '#3591b3',
  noise: '#7c8597',
};

const EXTRA = ['#c08a2d', '#b0559a', '#5f8f3c', '#4a6fa5'];

export const segmentColor = (code: SegmentCode | null | undefined, label?: string): string => {
  if (!code) return '#7c8597';
  const group = label ? /группа (\d+)/.exec(label) : null;
  if (group) return EXTRA[(Number(group[1]) - 2) % EXTRA.length];
  return SEGMENT_COLORS[code];
};

export const segmentBadgeStyle = (code: SegmentCode | null | undefined, label?: string) => {
  const color = segmentColor(code, label);
  return { backgroundColor: `${color}1f`, borderColor: `${color}55`, color };
};
