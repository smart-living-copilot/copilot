import { Switch } from '@/components/ui/switch';

interface JobEnabledFieldProps {
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
}

export function JobEnabledField({
  enabled,
  onEnabledChange,
}: JobEnabledFieldProps) {
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
