import fs from 'node:fs';
import path from 'node:path';

import type { Plugin, ResolvedConfig } from 'vite';

/**
 * Serves `/mockServiceWorker.js` from the MSW npm package during dev (no files under `/public`).
 * Copies that script into `outDir` on production builds so previews and Docker stay MSW-compatible in QA.
 *
 * Browser Service Workers cannot load TypeScript sources; MSW distributes a standalone JS shim.
 *
 * Ref: https://mswjs.io/docs/integrations/browser
 */
export function mswServiceWorkerPlugin(): Plugin {
  const workerPath = path.resolve(__dirname, 'node_modules/msw/lib/mockServiceWorker.js');

  let resolvedConfig: ResolvedConfig | undefined;

  return {
    name: 'msw-service-worker',
    configResolved(cfg: ResolvedConfig) {
      resolvedConfig = cfg;
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = req.url?.split('?')[0];
        if (pathname !== '/mockServiceWorker.js') {
          next();
          return;
        }
        fs.readFile(workerPath, (err, buf) => {
          if (err) {
            next(err);
            return;
          }
          res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
          res.end(buf);
        });
      });
    },
    closeBundle() {
      // Only emits during production builds (not dev server lifecycle).
      if (!resolvedConfig || resolvedConfig.command !== 'build') return;
      if (!fs.existsSync(workerPath)) return;

      const outDir = resolvedConfig.build.outDir;
      const dest = path.join(outDir, 'mockServiceWorker.js');
      fs.mkdirSync(outDir, { recursive: true });
      fs.copyFileSync(workerPath, dest);
    },
  };
}
