import { type JobRecord } from '@/lib/jobs-api';

export interface DegradedResourceMessage {
  name: string;
  message: string;
}

export function resourceHealthLabel(status: string | undefined): string {
  if (status === 'healthy') return 'Healthy';
  if (status === 'degraded') return 'Degraded';
  return 'Unknown';
}

export function resourceHealthBadgeVariant(status: string | undefined) {
  if (status === 'degraded') return 'destructive';
  if (status === 'healthy') return 'secondary';
  return 'outline';
}

export function resourceNameLabel(name: string): string {
  if (name === 'event_subscription') return 'Event subscription';
  if (name === 'virtual_record_thing') return 'Virtual record Thing';
  if (name === 'schedule') return 'Schedule';
  return name.replaceAll('_', ' ');
}

export function getDegradedResourceMessages(
  job: JobRecord | null,
): DegradedResourceMessage[] {
  const resources = job?.resource_health?.resources;
  if (!resources) return [];
  return Object.entries(resources)
    .filter(([, resource]) => resource.status === 'degraded')
    .map(([name, resource]) => ({
      name: resourceNameLabel(name),
      message: resource.message || 'Resource check failed.',
    }));
}
