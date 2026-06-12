import { AppShell } from '@/components/app-shell';
import { VirtualThingEditor } from '@/components/things/virtual-thing-editor';
import { getFirstSearchParam } from '@/lib/return-to';

export default async function EditVirtualThingPage({
  params,
  searchParams,
}: {
  params: Promise<{ thingId: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const [{ thingId }, query] = await Promise.all([params, searchParams]);

  return (
    <AppShell>
      <VirtualThingEditor
        returnTo={getFirstSearchParam(query.returnTo)}
        thingId={decodeURIComponent(thingId)}
      />
    </AppShell>
  );
}
