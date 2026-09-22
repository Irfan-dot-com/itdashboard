/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_NAME: string;
  readonly VITE_APP_ENV: 'development' | 'qa' | 'production';
  readonly VITE_API_BASE_URL: string;
  readonly VITE_ENABLE_MSW: string;
  readonly VITE_ENABLE_SIMULATION: string;
  readonly VITE_RELEASE_VERSION: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __APP_MODE__: string;
