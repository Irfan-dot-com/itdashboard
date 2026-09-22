import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils/cn';

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumbs" className="flex items-center gap-2 text-[12.5px]">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        const className = cn(
          isLast ? 'text-text font-medium' : 'text-text2 hover:text-text',
        );
        return (
          <span key={`${item.label}-${index}`} className="flex items-center gap-2">
            {item.to && !isLast ? (
              <Link to={item.to} className={className}>
                {item.label}
              </Link>
            ) : (
              <span className={className}>{item.label}</span>
            )}
            {!isLast ? <span className="text-text4">/</span> : null}
          </span>
        );
      })}
    </nav>
  );
}
