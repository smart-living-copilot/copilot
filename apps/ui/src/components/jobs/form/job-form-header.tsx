import { type ReactNode } from 'react';
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';

interface JobFormHeaderProps {
  title: string;
  description: string;
  cancelHref: string;
  submitLabel: string;
  submitIcon: ReactNode;
  isSubmitting: boolean;
  disabled: boolean;
}

export function JobFormHeader({
  title,
  description,
  cancelHref,
  submitLabel,
  submitIcon,
  isSubmitting,
  disabled,
}: JobFormHeaderProps) {
  return (
    <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" asChild>
          <Link href={cancelHref}>Cancel</Link>
        </Button>
        <Button type="submit" disabled={disabled}>
          {isSubmitting ? <Spinner className="size-4" /> : submitIcon}
          {submitLabel}
        </Button>
      </div>
    </section>
  );
}
