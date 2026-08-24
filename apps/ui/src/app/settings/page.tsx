'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Info,
  KeyRound,
  MessageSquareWarning,
  Settings,
  type LucideIcon,
} from 'lucide-react';

import { AppShell } from '@/components/app-shell';
import { ApiKeysPanel } from '@/components/settings/api-keys-panel';
import { ChatCleanupPanel } from '@/components/settings/chat-cleanup-panel';
import { SystemInfoPanel } from '@/components/settings/system-info-panel';
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';

const SETTINGS_TABS = ['chat-data', 'api-keys', 'system-info'] as const;

type SettingsTab = (typeof SETTINGS_TABS)[number];

function isSettingsTab(value: string | null): value is SettingsTab {
  return value !== null && SETTINGS_TABS.includes(value as SettingsTab);
}

const settingsNavItems: Array<{
  description: string;
  icon: LucideIcon;
  label: string;
  tab: SettingsTab;
}> = [
  {
    description: 'Batch delete saved chat history',
    icon: MessageSquareWarning,
    label: 'Chat data',
    tab: 'chat-data',
  },
  {
    description: 'Manage programmatic access',
    icon: KeyRound,
    label: 'API keys',
    tab: 'api-keys',
  },
  {
    description: 'Inspect the resolved runtime configuration',
    icon: Info,
    label: 'System info',
    tab: 'system-info',
  },
];

export default function SettingsPage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-7xl space-y-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0 space-y-1">
            <div className="flex min-w-0 items-center gap-2">
              <Settings className="size-5 shrink-0 text-muted-foreground" />
              <h1 className="truncate text-2xl font-semibold tracking-tight">
                Settings
              </h1>
            </div>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Manage workspace data, access, and integration settings.
            </p>
          </div>
        </div>

        <Suspense
          fallback={<SettingsTabLayout activeTab="chat-data" loading />}
        >
          <SettingsContent />
        </Suspense>
      </div>
    </AppShell>
  );
}

function SettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const activeTab: SettingsTab = isSettingsTab(requestedTab)
    ? requestedTab
    : 'chat-data';

  const handleTabChange = (tab: SettingsTab) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('tab', tab);
    router.replace(`/settings?${nextParams.toString()}`, { scroll: false });
  };

  return (
    <SettingsTabLayout activeTab={activeTab} onTabChange={handleTabChange} />
  );
}

function SettingsTabLayout({
  activeTab,
  loading = false,
  onTabChange,
}: {
  activeTab: SettingsTab;
  loading?: boolean;
  onTabChange?: (tab: SettingsTab) => void;
}) {
  return (
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <aside className="lg:sticky lg:top-4 lg:w-56 lg:shrink-0">
        <nav aria-label="Settings sections">
          <SidebarMenu>
            {settingsNavItems.map(({ description, icon: Icon, label, tab }) => (
              <SidebarMenuItem key={tab}>
                <SidebarMenuButton
                  disabled={!onTabChange}
                  isActive={activeTab === tab}
                  onClick={() => onTabChange?.(tab)}
                  tooltip={label}
                >
                  <Icon />
                  <span>{label}</span>
                  <span className="sr-only">{description}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading settings...</p>
        ) : activeTab === 'chat-data' ? (
          <ChatCleanupPanel />
        ) : activeTab === 'api-keys' ? (
          <ApiKeysPanel />
        ) : (
          <SystemInfoPanel />
        )}
      </div>
    </div>
  );
}
