import { ThingEditor } from '@/components/things/thing-editor';
import { AppShell } from '@/components/app-shell';
import { getFirstSearchParam } from '@/lib/return-to';

export default async function EditThingPage({
  params,
  searchParams,
}: {
  params: Promise<{ thingId: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const [{ thingId }, query] = await Promise.all([params, searchParams]);

  return (
    <AppShell>
      <ThingEditor
        mode="edit"
        returnTo={getFirstSearchParam(query.returnTo)}
        thingId={decodeURIComponent(thingId)}
      />
    </AppShell>
  );
}
