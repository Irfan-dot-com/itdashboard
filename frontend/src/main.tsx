import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './App';
import { env } from '@/lib/env/env';

import './styles/globals.css';

async function bootstrap(): Promise<void> {
  if (env.enableMsw && import.meta.env.DEV) {
    const { startMockWorker } = await import('@/mocks/browser');
    await startMockWorker();
  }

  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

void bootstrap();
