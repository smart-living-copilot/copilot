'use client';

import Link from 'next/link';
import { Plus, RefreshCw } from 'lucide-react';
import { useCallback, useState } from 'react';

import { JobDetailsDrawer } from '@/components/jobs/job-details-drawer';
import { VoiceModeToggle } from '@/components/jobs/job-speech-controls';
import { JobListFilters } from '@/components/jobs/list/job-list-filters';
import { JobListTable } from '@/components/jobs/list/job-list-table';
import { useJobsList } from '@/components/jobs/list/use-jobs-list';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { TooltipProvider } from '@/components/ui/tooltip';

export function JobsList() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const {
    activeTab,
    activeTabLabel,
    busyJobId,
    deferredSearch,
    isHydrated,
    isPending,
    runningJobId,
    search,
    setActiveTab,
    setSearch,
    tabCounts,
    visibleJobs,
    now,
    loadJobs,
    handleRun,
    handleToggleEnabled,
    handleCancel,
    handleDelete,
  } = useJobsList();

  const handleDrawerDeleted = useCallback(() => {
    setSelectedJobId(null);
    void loadJobs();
  }, [loadJobs]);

  return (
    <TooltipProvider>
      <div className="space-y-5">
        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight">Jobs</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Monitor background automations, review recent results, and manage
              scheduled work.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <VoiceModeToggle />
            <Button asChild>
              <Link href="/jobs/new">
                <Plus className="h-4 w-4" />
                Create
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => void loadJobs()}
              disabled={isHydrated ? isPending : false}
            >
              <RefreshCw
                className={isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
              />
              Refresh
            </Button>
          </div>
        </section>

        <section>
          <Card className="rounded-md border-border/70 shadow-sm shadow-black/5">
            <CardContent className="space-y-4 p-4 md:p-5">
              <JobListFilters
                activeTab={activeTab}
                activeTabLabel={activeTabLabel}
                search={search}
                tabCounts={tabCounts}
                visibleCount={visibleJobs.length}
                onSearchChange={setSearch}
                onTabChange={setActiveTab}
              />

              <JobListTable
                activeTab={activeTab}
                activeTabLabel={activeTabLabel}
                busyJobId={busyJobId}
                deferredSearch={deferredSearch}
                isHydrated={isHydrated}
                isPending={isPending}
                jobs={visibleJobs}
                now={now}
                runningJobId={runningJobId}
                onCancel={(jobId) => void handleCancel(jobId)}
                onClearSearch={() => setSearch('')}
                onDelete={(job) => void handleDelete(job)}
                onOpenDetails={setSelectedJobId}
                onRun={(jobId) => void handleRun(jobId)}
                onShowAll={() => setActiveTab('all')}
                onToggleEnabled={(job) => void handleToggleEnabled(job)}
              />
            </CardContent>
          </Card>
        </section>

        <JobDetailsDrawer
          jobId={selectedJobId}
          onDeleted={handleDrawerDeleted}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              setSelectedJobId(null);
            }
          }}
          open={selectedJobId !== null}
        />
      </div>
    </TooltipProvider>
  );
}
