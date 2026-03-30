import * as React from 'react';
import { ChevronDown } from 'lucide-react';

import { Button } from '@/components/ui/button';

type ButtonProps = React.ComponentPropsWithoutRef<typeof Button>;
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

type DropdownContentProps = React.ComponentPropsWithoutRef<
  typeof DropdownMenuContent
>;

interface SplitButtonProps {
  action: React.ReactNode;
  children: React.ReactNode;
  actionAsChild?: boolean;
  actionButtonProps?: Omit<
    ButtonProps,
    'asChild' | 'children' | 'variant' | 'size'
  >;
  align?: DropdownContentProps['align'];
  side?: DropdownContentProps['side'];
  sideOffset?: number;
  className?: string;
  contentClassName?: string;
  menuAriaLabel?: string;
  variant?: ButtonProps['variant'];
  size?: ButtonProps['size'];
}

export function SplitButton({
  action,
  children,
  actionAsChild = false,
  actionButtonProps,
  align = 'end',
  side,
  sideOffset = 4,
  className,
  contentClassName,
  menuAriaLabel = 'More actions',
  variant = 'outline',
  size = 'default',
}: SplitButtonProps) {
  return (
    <div className={cn('flex items-center', className)}>
      <Button
        {...actionButtonProps}
        asChild={actionAsChild}
        variant={variant}
        size={size}
        className={cn('rounded-r-none', actionButtonProps?.className)}
      >
        {action}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant={variant}
            size={size}
            aria-label={menuAriaLabel}
            className="rounded-l-none border-l-0 px-2.5"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent
          align={align}
          side={side}
          sideOffset={sideOffset}
          className={contentClassName}
        >
          {children}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
