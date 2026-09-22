import type { QueryClient } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';

import { TestAppProviders } from './TestAppProviders';

export function createRenderWrapper(options: {
  route?: string;
  queryClient?: QueryClient;
}): ({ children }: { children: ReactNode }) => ReactElement {
  const { route, queryClient } = options;
  return function renderWrapper({ children }: { children: ReactNode }) {
    return (
      <TestAppProviders route={route} queryClient={queryClient}>
        {children}
      </TestAppProviders>
    );
  };
}
