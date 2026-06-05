import { Switch } from '@/components/ui/switch';

interface JobEnabledFieldProps {
  compact?: boolean;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
}

export function JobEnabledField({
  compact = false,
  enabled,
  onEnabledChange,
}: JobEnabledFieldProps) {
  if (compact) {
    return (
      <div className="flex h-8 min-w-32 items-center justify-between gap-3 rounded-md border border-border/70 px-3">
        <span className="text-sm font-medium">Enabled</span>
        <Switch size="sm" checked={enabled} onCheckedChange={onEnabledChange} />
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between rounded-md border border-border/70 px-3 py-2">
      <div>
        <div className="text-sm font-medium">Enabled</div>
        <p className="text-xs text-muted-foreground">
          Paused jobs keep their history but never run automatically.
        </p>
      </div>
      <Switch checked={enabled} onCheckedChange={onEnabledChange} />
    </div>
  );
}
