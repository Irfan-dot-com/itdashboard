import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js';

let registered = false;

export function registerChartJs(): void {
  if (registered) return;
  ChartJS.register(
    LineController,
    LineElement,
    BarController,
    BarElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Filler,
    Tooltip,
  );
  registered = true;
}
