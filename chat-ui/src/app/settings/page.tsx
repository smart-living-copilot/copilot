'use client';

import { ApiKeysPanel } from '@/components/settings/api-keys-panel';
import { AppShell } from '@/components/app-shell';

export default function SettingsPage() {
  return (
    <AppShell>
      <div className="w-full space-y-8">
        <div className="flex items-center gap-3">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
            <p className="text-sm text-muted-foreground">
              Manage access and integration settings for your workspace.
            </p>
          </div>
        </div>

        <section id="api-keys">
          <ApiKeysPanel />
        </section>
      </div>
    </AppShell>
  );
}
