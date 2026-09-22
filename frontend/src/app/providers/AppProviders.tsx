import { RouterProvider } from 'react-router-dom';

import { ErrorBoundary } from '@/app/error/ErrorBoundary';
import { appRouter } from '@/app/router';

import { QueryProvider } from './QueryProvider';

export function AppProviders() {
  return (
    <ErrorBoundary>
      <QueryProvider>
        <RouterProvider
          router={appRouter}
          future={{ v7_startTransition: true }}
        />
      </QueryProvider>
    </ErrorBoundary>
  );
}
