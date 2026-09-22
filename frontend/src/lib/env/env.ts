import { envSchema } from './schema';

const parsed = envSchema.safeParse(import.meta.env);

if (!parsed.success) {
  console.error('Invalid environment configuration:', parsed.error.flatten().fieldErrors);
  throw new Error('Invalid environment configuration. See console for details.');
}

const raw = parsed.data;

export const env = {
  appName: raw.VITE_APP_NAME,
  appEnv: raw.VITE_APP_ENV,
  apiBaseUrl: raw.VITE_API_BASE_URL,
  enableMsw: raw.VITE_ENABLE_MSW === 'true',
  enableSimulation: raw.VITE_ENABLE_SIMULATION === 'true',
  releaseVersion: raw.VITE_RELEASE_VERSION,
  isDevelopment: raw.VITE_APP_ENV === 'development',
  isQa: raw.VITE_APP_ENV === 'qa',
  isProduction: raw.VITE_APP_ENV === 'production',
} as const;

export type Env = typeof env;
