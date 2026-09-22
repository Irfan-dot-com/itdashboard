import { z } from 'zod';

export const envSchema = z.object({
  VITE_APP_NAME: z.string().min(1),
  VITE_APP_ENV: z.enum(['development', 'qa', 'production']),
  VITE_API_BASE_URL: z.string().url(),
  VITE_ENABLE_MSW: z.enum(['true', 'false']),
  VITE_ENABLE_SIMULATION: z.enum(['true', 'false']),
  VITE_RELEASE_VERSION: z.string().min(1),
});

export type EnvSchema = z.infer<typeof envSchema>;
