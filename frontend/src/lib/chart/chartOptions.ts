import type { ChartData, ChartOptions } from 'chart.js';

export function sparkLineConfig(
  data: number[],
  color: string,
  options?: { suggestedMin?: number; suggestedMax?: number },
): { data: ChartData<'line'>; options: ChartOptions<'line'> } {
  return {
    data: {
      labels: data.map((_, index) => index),
      datasets: [
        {
          data,
          borderColor: color,
          backgroundColor: `${color}22`,
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 1.4,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: { display: false },
        y: {
          display: false,
          suggestedMin: options?.suggestedMin ?? 30,
          suggestedMax: options?.suggestedMax ?? 100,
        },
      },
    },
  };
}
