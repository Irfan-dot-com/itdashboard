# IT Dashboard - Development Guide

A quick-reference for every developer working on this codebase. Follow these
conventions so the dashboard stays consistent, testable, and easy to extend as
it moves from a static HTML prototype into a production-grade React application.

---

## Stack

| Layer | Technology |
|---|---|
| Framework | React + Vite |
| Language | TypeScript strict mode |
| Styling | Tailwind CSS + CSS custom property design tokens |
| Routing | React Router |
| Charts | Chart.js wrapped in React components |
| Data fetching | TanStack Query |
| API mocking | MSW |
| Unit/component tests | Vitest + React Testing Library |
| E2E tests | Playwright |
| Runtime container | Docker + Nginx |
| Quality gates | ESLint, Prettier, TypeScript, CI |

React owns the UI. Vite owns local development, bundling, and production builds.
This project should remain a client-rendered dashboard unless a future backend
or deployment model introduces a clear need for server rendering.

---

## Project Principles

- Prefer small, typed React components over large page files.
- Keep business logic outside JSX where it can be unit tested.
- Keep dashboard data access behind service functions and query hooks.
- Use Tailwind for normal layout, spacing, color, and typography.
- Use CSS files only for global tokens, keyframes, pseudo-elements, and styles
  that are awkward or fragile as Tailwind utilities.
- Avoid direct DOM manipulation. Use React state, props, refs, and effects.
- Avoid `dangerouslySetInnerHTML` unless the content is sanitized and reviewed.
- Keep the application usable offline during development through MSW fixtures.
- Introduce abstractions only when they remove real duplication or complexity.

---

## Folder Structure

Use the `src/` directory and group code by responsibility. This structure is
intended for a large dashboard with multiple product areas.

```txt
src/
├── main.tsx
├── App.tsx
├── vite-env.d.ts
│
├── app/
│   ├── providers/
│   │   ├── AppProviders.tsx
│   │   └── QueryProvider.tsx
│   ├── layouts/
│   │   └── DashboardLayout.tsx
│   ├── error/
│   │   ├── ErrorBoundary.tsx
│   │   └── NotFoundPage.tsx
│   ├── router.tsx
│   └── routeHandles.ts
│
├── pages/
│   ├── EstatePage/
│   ├── AlertsPage/
│   ├── AlertDetailPage/
│   ├── PropertyDetailPage/
│   ├── ExecutivePage/
│   ├── StubPage/
│   └── index.ts
│
├── components/
│   ├── layout/
│   │   ├── AppShell/
│   │   ├── Sidebar/
│   │   ├── Topbar/
│   │   ├── Breadcrumbs/
│   │   └── index.ts
│   ├── charts/
│   │   ├── SparkLineChart/
│   │   ├── BarChart/
│   │   └── index.ts
│   └── ui/
│       ├── Button/
│       ├── Card/
│       ├── Chip/
│       ├── DataTable/
│       ├── Dialog/
│       ├── EmptyState/
│       ├── LoadingState/
│       ├── SeverityPill/
│       ├── StatusDot/
│       └── index.ts
│
├── features/
│   ├── estate/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── types.ts
│   │   └── index.ts
│   ├── alerts/
│   ├── properties/
│   ├── executive/
│   ├── risk/
│   ├── simulation/
│   └── lumina/
│
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   ├── endpoints.ts
│   │   └── httpError.ts
│   ├── env/
│   │   ├── env.ts
│   │   └── schema.ts
│   ├── query/
│   │   ├── queryClient.ts
│   │   └── queryKeys.ts
│   ├── chart/
│   │   ├── registerChartJs.ts
│   │   └── chartOptions.ts
│   └── utils/
│       ├── cn.ts
│       ├── date.ts
│       ├── format.ts
│       └── invariant.ts
│
├── models/
│   ├── common.ts
│   ├── alerts.ts
│   ├── properties.ts
│   ├── events.ts
│   ├── metrics.ts
│   └── index.ts
│
├── constants/
│   ├── navigation.tsx
│   └── routes.ts
│
├── hooks/
│   ├── useClock.ts
│   ├── useTheme.ts
│   ├── useDebouncedValue.ts
│   └── useLocalStorage.ts
│
├── mocks/
│   ├── browser.ts
│   ├── server.ts
│   ├── handlers.ts
│   └── fixtures/
│
├── styles/
│   ├── globals.css
│   └── tokens.css
│
└── test/
    ├── setup.ts
    ├── test-utils.tsx
    └── accessibility.ts

vite.config.ts
vite-plugin-msw-worker.ts
index.html

e2e/
├── dashboard.spec.ts
├── alerts.spec.ts
└── simulation.spec.ts

docker/
└── nginx.conf
```

### Static assets (`public/` folder)

There is **`publicDir: false`** in `vite.config.ts`. Do not rely on committing ad-hoc scripts or mock workers under `/public`:

- Prefer TypeScript/React under `src/`.
- Favicons or future static files: either re-enable `public/` for those assets only, or import small assets from `src/` when Vite can bundle them.

### Folder Responsibilities

| Folder | Purpose |
|---|---|
| `src/app/` | Application composition: providers, layouts, error boundaries |
| `src/pages/` | Route-level pages composed from features and shared components |
| `src/components/` | Reusable UI components that do not own domain behavior |
| `src/features/` | Business features such as estate, alerts, simulation, Lumina |
| `src/lib/` | Shared infrastructure: API client, env parsing, query client, chart helpers, utilities |
| `src/models/` | Shared domain and API types |
| `src/constants/` | Navigation, route definitions, and static configuration |
| `src/hooks/` | Shared hooks used by multiple features |
| `src/mocks/` | MSW handlers and development/test fixtures |
| `src/styles/` | Global CSS, Tailwind entrypoint, and design tokens |
| `src/test/` | Test setup and reusable test helpers |
| `e2e/` | Playwright browser tests |
| `docker/` | Nginx container support files |
| `vite-plugin-msw-worker.ts` (repo root) | Serves `/mockServiceWorker.js` from the MSW package in dev; copies it into `dist/` on build (no custom JS in `/public`) |

---

## Application Entry

Keep `main.tsx` small. It should only mount React and wire the top-level app.

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';

import { App } from './App';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

`App.tsx` mounts providers; the **data router** is created in `src/app/router.tsx` and passed to `RouterProvider` in `AppProviders`.

```tsx
import { AppProviders } from '@/app/providers/AppProviders';
import { useTheme } from '@/hooks/useTheme';

export function App() {
  useTheme();
  return <AppProviders />;
}
```

---

## Routing

Use **React Router's data router**: `createBrowserRouter` and `RouterProvider`. This is required for hooks such as `useMatches`, which the shell uses for breadcrumb `handle` data.

Keep canonical path strings in `src/constants/routes.ts`. Define the route tree in **`src/app/router.tsx`**.

```ts
export const ROUTES = {
  estate: '/',
  alerts: '/alerts',
  alertDetail: '/alerts/:alertId',
  propertyDetail: '/properties/:propertyId',
  executive: '/executive',
  risk: '/risk',
} as const;
```

Route modules should compose pages, not contain feature logic. Prefer a `handle` object for UI metadata (breadcrumbs):

```tsx
import { createBrowserRouter } from 'react-router-dom';

import { DashboardLayout } from '@/app/layouts/DashboardLayout';
import { AlertsPage, EstatePage } from '@/pages';

export const appRouter = createBrowserRouter([
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      {
        index: true,
        element: <EstatePage />,
        handle: { breadcrumbs: [{ label: 'Estate' }] },
      },
      {
        path: 'alerts',
        element: <AlertsPage />,
        handle: {
          breadcrumbs: [{ label: 'Estate', to: '/' }, { label: 'Alerts' }],
        },
      },
    ],
  },
]);
```

`AppProviders` renders `<RouterProvider router={appRouter} />`.

Use URL params for shareable state such as selected alert IDs and property IDs.
Use local React state for temporary UI state such as open panels and filters.

---

## Environment Setup

Vite only exposes environment variables prefixed with `VITE_`. Never put
secrets in frontend environment variables. Anything shipped to the browser is
public.

### Environment Files

Use separate files for local development, QA, and production:

```txt
.env.example
.env.development
.env.qa
.env.production
.env.local
```

Commit `.env.example` only. Do not commit real environment files containing
environment-specific URLs, keys, or operational settings.

Example `.env.example`:

```bash
VITE_APP_NAME="IT Dashboard"
VITE_APP_ENV="development"
VITE_API_BASE_URL="http://localhost:8080"
VITE_ENABLE_MSW="true"
VITE_ENABLE_SIMULATION="true"
VITE_RELEASE_VERSION="local"
```

Recommended environment usage:

| Environment | File | Purpose |
|---|---|---|
| Development | `.env.development` + `.env.local` | Local developer machine |
| QA | `.env.qa` | Deployed test/staging environment |
| Production | `.env.production` | Real users and production API |

### Environment Rules

- `VITE_APP_ENV` must be one of `development`, `qa`, or `production`.
- `VITE_API_BASE_URL` must point to the matching backend/API gateway.
- `VITE_ENABLE_MSW` should be `true` only for local development and isolated tests.
- `VITE_ENABLE_SIMULATION` can be enabled in development and QA, but should be
  disabled in production unless explicitly approved.
- Do not store secrets, tokens, passwords, or private keys in Vite env vars.
- Validate env values at startup so bad deployments fail loudly.

### Typed Env Access

Access env values through one module instead of reading `import.meta.env`
throughout the app.

```ts
// src/lib/env/env.ts
export const env = {
  appName: import.meta.env.VITE_APP_NAME,
  appEnv: import.meta.env.VITE_APP_ENV,
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
  enableMsw: import.meta.env.VITE_ENABLE_MSW === 'true',
  enableSimulation: import.meta.env.VITE_ENABLE_SIMULATION === 'true',
  releaseVersion: import.meta.env.VITE_RELEASE_VERSION,
} as const;
```

Use runtime validation if the project adds `zod`:

```ts
// src/lib/env/schema.ts
import { z } from 'zod';

const schema = z.object({
  VITE_APP_NAME: z.string().min(1),
  VITE_APP_ENV: z.enum(['development', 'qa', 'production']),
  VITE_API_BASE_URL: z.string().url(),
  VITE_ENABLE_MSW: z.enum(['true', 'false']),
  VITE_ENABLE_SIMULATION: z.enum(['true', 'false']),
  VITE_RELEASE_VERSION: z.string().min(1),
});

export const parsedEnv = schema.parse(import.meta.env);
```

### Build Modes

Use Vite modes to build environment-specific bundles:

```bash
npm run build:dev
npm run build:qa
npm run build:prod
```

Recommended scripts:

```json
{
  "dev": "vite --mode development",
  "dev:qa": "vite --mode qa",
  "build:dev": "tsc --noEmit && vite build --mode development",
  "build:qa": "tsc --noEmit && vite build --mode qa",
  "build:prod": "tsc --noEmit && vite build --mode production"
}
```

---

## Component Structure

Every reusable component lives in its own named folder:

```txt
ComponentName/
├── ComponentName.tsx
├── ComponentName.test.tsx
└── index.ts
```

Use named exports:

```tsx
export function SeverityPill() {
  return null;
}
```

Keep `index.ts` files thin:

```ts
export { SeverityPill } from './SeverityPill';
```

Only add a component CSS file when Tailwind is not the right tool:

```txt
ComponentName/
├── ComponentName.tsx
├── ComponentName.css
├── ComponentName.test.tsx
└── index.ts
```

Components in `src/components/ui/` should be generic. They must not import from
feature folders.

---

## Feature Structure

Feature folders own domain-specific UI, hooks, services, utilities, and tests:

```txt
features/alerts/
├── components/
│   ├── AlertQueue/
│   │   ├── AlertQueue.tsx
│   │   ├── AlertQueue.test.tsx
│   │   └── index.ts
│   ├── AlertHero/
│   └── AlertTimeline/
├── hooks/
│   ├── useAlerts.ts
│   └── useAlertDetail.ts
├── services/
│   └── alertsService.ts
├── utils/
│   └── alertSeverity.ts
├── types.ts
└── index.ts
```

Use this pattern when code belongs to one business area. Promote code to
`src/components/`, `src/hooks/`, or `src/lib/` only when it is genuinely shared.

Feature public APIs should be exported from `index.ts`. Other parts of the app
should not deep-import into feature internals.

---

## Styling Rules

### Tailwind First

Use Tailwind utility classes for layout, spacing, typography, borders, and most
visual states.

Use a helper such as `cn()` for conditional class names:

```ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

### Design Tokens

Global CSS variables live in `src/styles/tokens.css` and are imported by
`src/styles/globals.css`. Keep theme colors as tokens and map Tailwind colors to
those tokens.

Use token-based classes instead of hard-coded one-off colors where possible:

```tsx
<div className="border-border bg-surface text-text">
  Dashboard card
</div>
```

Avoid hard-coded hex values in components:

```tsx
// Avoid
<div className="bg-[#1a1a17] text-[#e8e6dd]" />
```

### Global CSS

Global CSS is allowed for:

- Tailwind directives
- CSS variables
- base element styles
- keyframes
- reusable low-level utilities
- third-party library overrides

Do not place component-specific styling in `globals.css`.

---

## Import Conventions

Use the `@/` alias for imports from `src/`:

```ts
import { AppShell } from '@/components/layout';
import { AlertQueue } from '@/features/alerts';
import type { AlertSummary } from '@/models';
```

Do not use `.js` extensions in TypeScript source imports:

```ts
// Correct
import { useTheme } from '@/hooks/useTheme';

// Avoid
import { useTheme } from '@/hooks/useTheme.js';
```

Use `import type` for types:

```ts
import type { Severity } from '@/models';
```

Prefer barrel imports for public feature/component APIs. Deep imports are
allowed only inside the same feature folder.

---

## Domain Models

All shared API and domain types live in `src/models/`. Do not define long-lived
domain types inside component files.

```ts
// src/models/alerts.ts
export type Severity = 'p1' | 'p2' | 'p3' | 'info';

export interface AlertSummary {
  id: string;
  severity: Severity;
  siteName: string;
  summary: string;
  createdAt: string;
}
```

Feature-only types can live in the feature folder:

```txt
features/simulation/types.ts
```

Move a type to `src/models/` when more than one feature depends on it.

---

## Data Fetching and State

Use TanStack Query for server/cache state. Components and pages should not call
`fetch` directly.

```ts
export function useAlerts() {
  return useQuery({
    queryKey: queryKeys.alerts.list(),
    queryFn: alertsService.list,
  });
}
```

Use local React state for UI-only state:

- open/closed panels
- selected tabs
- temporary filters
- simulation running state
- client-only theme state

Use URL state for shareable route state:

- selected alert
- selected property
- dashboard section
- query-string filters that should survive refresh/share

Avoid global state by default. Add a global store only when state is genuinely
shared across distant parts of the tree and cannot be represented cleanly in the
URL, React Query, or colocated component state.

---

## API and Mocking

MSW is the source of truth for local development without a backend.

```txt
src/mocks/
├── browser.ts
├── server.ts
├── handlers.ts
└── fixtures/
```

- `browser.ts` starts MSW in local development.
- `server.ts` starts MSW in Vitest.
- `handlers.ts` contains route handlers.
- `fixtures/` contains typed mock data.

Add an MSW handler whenever a new API endpoint is introduced. Tests should mock
network behavior through MSW rather than mocking query hooks directly.

### MSW Service Worker (browser)

Browsers cannot register a TypeScript file as a Service Worker. MSW ships a small
**JavaScript** worker script (`node_modules/msw/lib/mockServiceWorker.js`).

Do **not** commit that file under `public/`. This project uses **`publicDir: false`**
and `vite-plugin-msw-worker.ts` to:

1. Serve `/mockServiceWorker.js` with `Content-Type: application/javascript` during `vite dev`.
2. Copy the same file into `dist/` during `vite build` (Docker and `vite preview`).

`src/mocks/browser.ts` continues to call `worker.start({ serviceWorker: { url: '/mockServiceWorker.js' } })`.

---

## Charts

Chart.js usage must be wrapped in React components. Do not create charts by
querying the DOM with `document.getElementById`.

Preferred pattern:

```tsx
import { Line } from 'react-chartjs-2';

interface SparkLineChartProps {
  data: number[];
  color: string;
}

export function SparkLineChart({ data, color }: SparkLineChartProps) {
  return (
    <Line
      data={{
        labels: data.map((_, index) => index),
        datasets: [{ data, borderColor: color, pointRadius: 0 }],
      }}
      options={{
        plugins: { legend: { display: false } },
        scales: { x: { display: false }, y: { display: false } },
        maintainAspectRatio: false,
      }}
    />
  );
}
```

Keep reusable chart options in `src/lib/chart/chartOptions.ts`. Register Chart.js
controllers once in `src/lib/chart/registerChartJs.ts`.

---

## Theming

The app supports dark mode by default and optional light mode.

- Theme tokens live in global CSS variables.
- `useTheme` reads/writes `localStorage`.
- The theme toggle updates a class on the root element.
- User choice takes precedence over system preference.

Do not scatter theme-specific values through component code. Components should
consume theme tokens through Tailwind classes or CSS variables.

---

## Testing Strategy

Testing is part of the implementation, not a final cleanup step.

| Test type | Tooling | Use for |
|---|---|---|
| Unit tests | Vitest | formatters, mappers, query keys, chart option builders |
| Component tests | React Testing Library | cards, tables, filters, buttons, chart wrappers |
| Feature tests | Vitest + Testing Library + MSW | alert queue, estate navigation, Lumina responses |
| E2E tests | Playwright | critical user journeys in the browser |
| Accessibility checks | Testing Library + axe or Playwright axe | important UI states and pages |

Recommended test layout:

```txt
src/
├── features/
│   └── alerts/
│       ├── components/
│       │   └── AlertQueue/
│       │       ├── AlertQueue.tsx
│       │       └── AlertQueue.test.tsx
│       └── hooks/
│           ├── useAlerts.ts
│           └── useAlerts.test.ts
│
└── test/
    ├── setup.ts
    ├── test-utils.tsx
    └── accessibility.ts

e2e/
├── dashboard.spec.ts
├── alerts.spec.ts
└── simulation.spec.ts
```

### What to Test

- Utility functions: severity mapping, score grading, formatting.
- Components: render states, user interactions, accessibility labels.
- Feature flows: estate card click opens property detail, alert row opens detail.
- Data states: loading, error, empty, and populated states.
- E2E journeys: dashboard load, navigation, alert detail, simulation toggle,
  theme toggle, and cross-dashboard handoff links.

### Testing Rules

- Test behavior, not implementation details.
- Prefer accessible queries: `getByRole`, `getByLabelText`, `getByText`.
- Do not assert Tailwind class strings unless the class is the behavior.
- Mock network calls with MSW.
- Keep test fixtures typed and close to real API responses.
- Use `renderWithProviders` for components that need router/query/theme context.

---

## Docker Container

The frontend should be built as static assets and served from a small Nginx
container. Do not run the Vite dev server in production.

### Recommended Files

```txt
Dockerfile
.dockerignore
docker/
├── nginx.conf
└── entrypoint.sh
```

### Dockerfile

Use a multi-stage build:

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG VITE_APP_ENV=production
ARG VITE_API_BASE_URL
ARG VITE_ENABLE_MSW=false
ARG VITE_ENABLE_SIMULATION=false
ARG VITE_RELEASE_VERSION=unknown
ENV VITE_APP_ENV=$VITE_APP_ENV
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_ENABLE_MSW=$VITE_ENABLE_MSW
ENV VITE_ENABLE_SIMULATION=$VITE_ENABLE_SIMULATION
ENV VITE_RELEASE_VERSION=$VITE_RELEASE_VERSION
RUN npm run build:prod

FROM nginx:1.27-alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### `.dockerignore`

```txt
node_modules
dist
coverage
playwright-report
test-results
.env*
!.env.example
.git
.DS_Store
```

### Nginx Config

React Router needs SPA fallback support:

```nginx
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /assets/ {
    try_files $uri =404;
    add_header Cache-Control "public, max-age=31536000, immutable";
  }

  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

### Build and Run Locally

```bash
docker build \
  --build-arg VITE_APP_ENV=production \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  --build-arg VITE_ENABLE_MSW=false \
  --build-arg VITE_ENABLE_SIMULATION=false \
  --build-arg VITE_RELEASE_VERSION=local-docker \
  -t it-dashboard-frontend .

docker run --rm -p 8080:80 it-dashboard-frontend
```

Open:

```txt
http://localhost:8080
```

### Docker Compose for Local QA

Use Compose when running the frontend with a backend/API gateway locally:

```yaml
services:
  frontend:
    build:
      context: .
      args:
        VITE_APP_ENV: qa
        VITE_API_BASE_URL: http://localhost:8080
        VITE_ENABLE_MSW: "false"
        VITE_ENABLE_SIMULATION: "true"
        VITE_RELEASE_VERSION: local-compose
    ports:
      - "5174:80"
    restart: unless-stopped
```

### Container Rules

- The production container serves static files only.
- Build-time `VITE_` variables are baked into the generated JavaScript bundle.
- Do not pass secrets into the frontend container.
- Use Nginx SPA fallback so direct navigation to `/alerts/123` works.
- Run `npm run build:prod` before publishing an image.
- Tag images with a release version, commit SHA, or CI build number.

---

## Scripts

Recommended `package.json` scripts:

```json
{
  "dev": "vite --mode development",
  "dev:qa": "vite --mode qa",
  "build": "npm run build:prod",
  "build:dev": "tsc --noEmit && vite build --mode development",
  "build:qa": "tsc --noEmit && vite build --mode qa",
  "build:prod": "tsc --noEmit && vite build --mode production",
  "preview": "vite preview",
  "lint": "eslint .",
  "typecheck": "tsc --noEmit",
  "test": "vitest",
  "test:watch": "vitest --watch",
  "test:coverage": "vitest run --coverage",
  "test:e2e": "playwright test",
  "test:e2e:ui": "playwright test --ui",
  "format": "prettier --write .",
  "format:check": "prettier --check ."
}
```

Run the full local quality gate before opening a PR:

```bash
npm run typecheck
npm run lint
npm run test
npm run test:e2e
npm run build
```

---

## Running Locally

Install dependencies:

```bash
npm install
```

Run development mode:

```bash
npm run dev
```

Run against QA-like env values:

```bash
npm run dev:qa
```

The app should run at:

```txt
http://localhost:5173
```

No backend is required for local development while MSW fixtures are available.

---

## CI and Deployment Gates

Every pull request should run:

```bash
npm run typecheck
npm run lint
npm run test
npm run build:qa
```

Every release candidate should run:

```bash
npm run test:coverage
npm run test:e2e
npm run build:prod
docker build -t it-dashboard-frontend:<release-version> .
```

Deployment promotion order:

```txt
development -> qa -> production
```

Production deployments must use production env values, disabled MSW, and a
traceable release version.

---

## Migration Notes from `it_dashboard.html`

The current HTML prototype should be migrated in slices:

1. Move global theme tokens and base styles into Tailwind/global CSS.
2. Convert shell layout into `AppShell`, `Sidebar`, `Topbar`, and `Breadcrumbs`.
3. Move static arrays into typed fixtures/constants.
4. Convert estate cards, alert queue, KPI cards, and tables into components.
5. Replace `innerHTML` rendering with React JSX.
6. Replace manual event listeners with React event handlers.
7. Replace `document.getElementById` chart setup with React chart components.
8. Move simulation timers into a feature hook.
9. Add unit and component tests for each migrated slice.
10. Add Playwright tests for the main user journeys.

Do not migrate everything in one large change. Keep each PR small enough to
review and test confidently.
