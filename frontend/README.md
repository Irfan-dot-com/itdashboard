# IT Dashboard - Frontend

React + Vite + TypeScript + Tailwind CSS dashboard for Estate IT (Thwaites Group).

See [`docs/DEVELOPMENT_GUIDE.md`](./docs/DEVELOPMENT_GUIDE.md) for the full
project conventions, folder structure, testing strategy, environment setup, and
Docker instructions.

## Quick Start

```bash
npm install
npm run dev
```

Open http://localhost:5173.

MSW provides mock API responses in development; no backend is required. The
Service Worker script is served from `node_modules/msw` by Vite (`vite-plugin-msw-worker.ts`), not from a `public/` file.

## Common Scripts

```bash
npm run dev            # local development (development mode)
npm run dev:qa         # local development against QA env values
npm run build:prod     # production build
npm run preview        # preview the production build
npm run typecheck      # TypeScript only
npm run lint           # ESLint
npm run test           # Vitest (watch mode)
npm run test:coverage  # Vitest with coverage
npm run test:e2e       # Playwright end-to-end
npm run format         # Prettier
```

## Environment

Copy `.env.example` to `.env.local` for any per-developer overrides:

```bash
cp .env.example .env.local
```

Environments:

- `.env.development`
- `.env.qa`
- `.env.production`

## Docker

Build a production image and run it locally:

```bash
docker build \
  --build-arg VITE_APP_ENV=production \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  --build-arg VITE_RELEASE_VERSION=local-docker \
  -t it-dashboard-frontend .

docker run --rm -p 8080:80 it-dashboard-frontend
```

Or with Compose for a local QA-style run:

```bash
docker compose up --build
```
