import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/lib/utils/cn';

type Variant = 'default' | 'prime' | 'danger' | 'ghost';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
}

const variantClass: Record<Variant, string> = {
  default: 'btn',
  prime: 'btn btn-prime',
  danger: 'btn btn-danger',
  ghost: 'btn btn-ghost',
};

export function Button({ variant = 'default', icon, className, children, type = 'button', ...rest }: ButtonProps) {
  return (
    <button type={type} className={cn(variantClass[variant], className)} {...rest}>
      {icon ? <span className="inline-flex">{icon}</span> : null}
      {children}
    </button>
  );
}
