import { type ReactNode } from 'react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

interface JobFormCardProps {
  title: string;
  description: string;
  children: ReactNode;
  contentClassName?: string;
  headerAction?: ReactNode;
}

export function JobFormCard({
  title,
  description,
  children,
  contentClassName,
  headerAction,
}: JobFormCardProps) {
  return (
    <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
      <CardHeader className="border-b border-border/70">
        {headerAction ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
            {headerAction}
          </div>
        ) : (
          <>
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </>
        )}
      </CardHeader>
      <CardContent className={contentClassName}>{children}</CardContent>
    </Card>
  );
}
