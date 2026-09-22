import { AppProviders } from '@/app/providers/AppProviders';
import { useTheme } from '@/hooks/useTheme';

export function App() {
  useTheme();
  return <AppProviders />;
}
