'use client';

import { ThingFileUpload } from '@/components/things/thing-file-upload';
import { AppShell } from '@/components/app-shell';

export default function UploadThingsPage() {
  return (
    <AppShell>
      <ThingFileUpload />
    </AppShell>
  );
}
