'use client';

import type { ComponentProps } from 'react';
import { cn } from '@/lib/utils';

export const mono = 'font-mono text-[11px] tracking-tight';

export function ShimmerLabel({
  active = true,
  className,
  ...props
}: ComponentProps<'span'> & { active?: boolean }) {
  return (
    <span
      className={cn(active && 'shimmer motion-reduce:animate-none', className)}
      {...props}
    />
  );
}
