'use client';

import { Loader2, Power } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { Toggle } from '@/components/ui/toggle';
import {
  fetchVirtualThingDefinition,
  setVirtualThingStatus,
  type VirtualThingStatus,
} from '@/lib/virtual-things-api';

/**
 * Compact enable/disable control for a Virtual Thing on the detail page.
 * Disabling removes the produced Thing from the catalog, so we navigate back to
 * the list afterwards rather than leaving the user on a stale page.
 */
export function VirtualThingStatusToggle({ thingId }: { thingId: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<VirtualThingStatus | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchVirtualThingDefinition(thingId, true)
      .then((definition) => {
        if (!cancelled) setStatus(definition.status);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [thingId]);

  if (status === null) return null;

  async function handleChange(checked: boolean) {
    const nextStatus = checked ? 'active' : 'disabled';
    setIsBusy(true);
    try {
      const result = await setVirtualThingStatus(thingId, nextStatus);
      if (result.validationReport) {
        toast.error('Validation failed — open Edit bindings to resolve.');
        return;
      }
      setStatus(nextStatus);
      if (nextStatus === 'disabled') {
        toast.success('Disabled — removed from the catalog.');
        router.push('/things');
      } else {
        toast.success('Enabled');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Update failed');
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <Toggle
      variant="outline"
      pressed={status === 'active'}
      disabled={isBusy}
      onPressedChange={(pressed) => void handleChange(pressed)}
      aria-label={
        status === 'active' ? 'Disable Virtual Thing' : 'Enable Virtual Thing'
      }
    >
      {isBusy ? <Loader2 className="animate-spin" /> : <Power />}
      {status === 'active' ? 'Enabled' : 'Disabled'}
    </Toggle>
  );
}
