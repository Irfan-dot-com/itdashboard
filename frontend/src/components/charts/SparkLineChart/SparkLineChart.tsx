import { Line } from 'react-chartjs-2';
import { useMemo } from 'react';

import { registerChartJs } from '@/lib/chart/registerChartJs';
import { sparkLineConfig } from '@/lib/chart/chartOptions';

registerChartJs();

interface SparkLineChartProps {
  data: number[];
  color: string;
  suggestedMin?: number;
  suggestedMax?: number;
  ariaLabel?: string;
}

export function SparkLineChart({ data, color, suggestedMin, suggestedMax, ariaLabel }: SparkLineChartProps) {
  const { data: chartData, options } = useMemo(
    () => sparkLineConfig(data, color, { suggestedMin, suggestedMax }),
    [data, color, suggestedMin, suggestedMax],
  );

  return (
    <div className="h-full w-full" role="img" aria-label={ariaLabel ?? 'spark line'}>
      <Line data={chartData} options={options} />
    </div>
  );
}
