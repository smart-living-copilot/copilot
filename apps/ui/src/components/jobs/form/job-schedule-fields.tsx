import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import {
  type JobScheduleFormFields,
  type JobScheduleKind,
} from './job-form-model';

interface JobScheduleFieldsProps extends JobScheduleFormFields {
  scheduleKind: JobScheduleKind;
  onCronExpressionChange: (value: string) => void;
  onCronTimezoneChange: (value: string) => void;
  onIntervalSecondsChange: (value: string) => void;
  onRunAtChange: (value: string) => void;
  onScheduleKindChange?: (value: JobScheduleKind) => void;
}

function IntervalField({
  intervalSeconds,
  onIntervalSecondsChange,
}: Pick<
  JobScheduleFieldsProps,
  'intervalSeconds' | 'onIntervalSecondsChange'
>) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Interval seconds</label>
      <Input
        type="number"
        min="1"
        value={intervalSeconds}
        onChange={(event) => onIntervalSecondsChange(event.target.value)}
        placeholder="300"
      />
    </div>
  );
}

function RunAtField({
  runAt,
  onRunAtChange,
}: Pick<JobScheduleFieldsProps, 'onRunAtChange' | 'runAt'>) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Run once at</label>
      <Input
        type="datetime-local"
        value={runAt}
        onChange={(event) => onRunAtChange(event.target.value)}
      />
    </div>
  );
}

function CronFields({
  cronExpression,
  cronTimezone,
  onCronExpressionChange,
  onCronTimezoneChange,
}: Pick<
  JobScheduleFieldsProps,
  | 'cronExpression'
  | 'cronTimezone'
  | 'onCronExpressionChange'
  | 'onCronTimezoneChange'
>) {
  return (
    <>
      <div className="space-y-2">
        <label className="text-sm font-medium">Cron expression</label>
        <Input
          value={cronExpression}
          onChange={(event) => onCronExpressionChange(event.target.value)}
          placeholder="0 9 * * sun"
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">Cron timezone</label>
        <Input
          value={cronTimezone}
          onChange={(event) => onCronTimezoneChange(event.target.value)}
          placeholder="Europe/Berlin"
        />
      </div>
    </>
  );
}

export function JobScheduleFields({
  scheduleKind,
  intervalSeconds,
  runAt,
  cronExpression,
  cronTimezone,
  onCronExpressionChange,
  onCronTimezoneChange,
  onIntervalSecondsChange,
  onRunAtChange,
  onScheduleKindChange,
}: JobScheduleFieldsProps) {
  const isEditable = Boolean(onScheduleKindChange);
  const className =
    isEditable || scheduleKind === 'cron'
      ? 'grid gap-4 sm:grid-cols-2'
      : 'sm:max-w-xs';

  return (
    <div className={className}>
      {onScheduleKindChange ? (
        <div className="space-y-2">
          <label className="text-sm font-medium">Schedule</label>
          <Select
            value={scheduleKind}
            onValueChange={(value) =>
              onScheduleKindChange(value as JobScheduleKind)
            }
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="interval">Interval</SelectItem>
              <SelectItem value="cron">Cron</SelectItem>
              <SelectItem value="once">Once</SelectItem>
            </SelectContent>
          </Select>
        </div>
      ) : null}

      {scheduleKind === 'interval' ? (
        <IntervalField
          intervalSeconds={intervalSeconds}
          onIntervalSecondsChange={onIntervalSecondsChange}
        />
      ) : null}

      {scheduleKind === 'once' ? (
        <RunAtField runAt={runAt} onRunAtChange={onRunAtChange} />
      ) : null}

      {scheduleKind === 'cron' ? (
        <CronFields
          cronExpression={cronExpression}
          cronTimezone={cronTimezone}
          onCronExpressionChange={onCronExpressionChange}
          onCronTimezoneChange={onCronTimezoneChange}
        />
      ) : null}
    </div>
  );
}
