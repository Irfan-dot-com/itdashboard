import type { QueryClient } from '@tanstack/react-query';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';

import { createRenderWrapper } from './create-render-wrapper';

interface ProviderOptions {
  route?: string;
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  options: ProviderOptions & Omit<RenderOptions, 'wrapper'> = {},
): RenderResult {
  const { route, queryClient, ...renderOptions } = options;
  const Wrapper = createRenderWrapper({ route, queryClient });
  return render(ui, {
    wrapper: Wrapper,
    ...renderOptions,
  });
}
