import { Bell, Gauge, Zap } from 'lucide-react';

import { cn } from '@/lib/utils';

const ICONS = {
  property: Gauge,
  action: Zap,
  event: Bell,
} as const;

export function AffordanceIcon({
  type,
  className,
}: {
  type: string;
  className?: string;
}) {
  const Icon = ICONS[type as keyof typeof ICONS] ?? Gauge;
  return (
    <Icon
      aria-hidden
      className={cn('size-4 shrink-0 text-muted-foreground', className)}
    />
  );
}
