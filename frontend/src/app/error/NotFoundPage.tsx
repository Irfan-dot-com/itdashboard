import { Link } from 'react-router-dom';

import { ROUTES } from '@/constants/routes';

export function NotFoundPage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <div className="text-3xl font-medium tracking-tight mb-2">404</div>
        <div className="text-sm text-text2 mb-4">This page does not exist.</div>
        <Link to={ROUTES.estate} className="btn btn-prime inline-flex">
          Back to Estate
        </Link>
      </div>
    </div>
  );
}
