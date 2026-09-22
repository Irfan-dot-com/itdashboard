import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { createTestQueryClient } from './test-query-client';

interface TestAppProvidersProps {
  children: ReactNode;
  route?: string;
  queryClient?: QueryClient;
}

export function TestAppProviders({ children, route = '/', queryClient }: TestAppProvidersProps) {
  const client = queryClient ?? createTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter
        future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
        initialEntries={[route]}
      >
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
}
