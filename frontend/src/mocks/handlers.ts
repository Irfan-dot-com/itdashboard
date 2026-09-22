import { http, HttpResponse } from 'msw';

import { env } from '@/lib/env/env';

import { ALERT_FIXTURES, mergeAlertDetail } from './fixtures/alerts';
import { SITE_FIXTURES } from './fixtures/sites';

const base = env.apiBaseUrl.replace(/\/$/, '');

export const handlers = [
  http.get(`${base}/v1/sites`, () => HttpResponse.json(SITE_FIXTURES)),
  http.get(`${base}/v1/sites/:siteId`, ({ params }) => {
    const site = SITE_FIXTURES.find((s) => s.id === params.siteId);
    if (!site) return HttpResponse.json({ error: 'Not found' }, { status: 404 });
    return HttpResponse.json(site);
  }),
  http.get(`${base}/v1/alerts`, () => HttpResponse.json(ALERT_FIXTURES)),
  http.get(`${base}/v1/alerts/:alertId`, ({ params }) =>
    HttpResponse.json(mergeAlertDetail(String(params.alertId))),
  ),
];
