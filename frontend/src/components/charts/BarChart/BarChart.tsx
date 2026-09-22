import { Bar } from 'react-chartjs-2';
import type { ChartData, ChartOptions } from 'chart.js';
import { useMemo } from 'react';

import { registerChartJs } from '@/lib/chart/registerChartJs';

registerChartJs();

interface Dataset {
  label: string;
  data: number[];
  color: string;
}

interface BarChartProps {
  labels: string[];
  datasets: Dataset[];
  ariaLabel?: string;
}

export function BarChart({ labels, datasets, ariaLabel }: BarChartProps) {
  const data: ChartData<'bar'> = useMemo(
    () => ({
      labels,
      datasets: datasets.map((d) => ({
        label: d.label,
        data: d.data,
        backgroundColor: d.color,
        borderRadius: 2,
        barPercentage: 0.7,
        categoryPercentage: 0.6,
      })),
    }),
    [labels, datasets],
  );

  const options: ChartOptions<'bar'> = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        x: {
          display: true,
          grid: { display: false },
          ticks: { color: '#6e6a5e', font: { size: 9, family: 'IBM Plex Mono' } },
        },
        y: { display: false, stacked: false },
      },
    }),
    [],
  );

  return (
    <div className="h-full w-full" role="img" aria-label={ariaLabel ?? 'bar chart'}>
      <Bar data={data} options={options} />
    </div>
  );
}
