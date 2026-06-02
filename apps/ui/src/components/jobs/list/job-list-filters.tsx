import { Search } from 'lucide-react';

import {
  JOB_TABS,
  type JobTabCounts,
  type JobTabValue,
} from '@/components/jobs/list/job-list-formatters';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

const JOB_TABS_TRIGGER_CLASSNAME =
  'flex-none rounded-none border-b-2 border-transparent px-4 py-2.5 font-medium text-muted-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none data-active:border-primary data-active:bg-transparent data-active:text-foreground data-active:shadow-none';

interface JobListFiltersProps {
  activeTab: JobTabValue;
  activeTabLabel: string;
  search: string;
  tabCounts: JobTabCounts;
  visibleCount: number;
  onSearchChange: (value: string) => void;
  onTabChange: (value: JobTabValue) => void;
}

export function JobListFilters({
  activeTab,
  activeTabLabel,
  search,
  tabCounts,
  visibleCount,
  onSearchChange,
  onTabChange,
}: JobListFiltersProps) {
  return (
    <>
      <Tabs
        value={activeTab}
        onValueChange={(value) => onTabChange(value as JobTabValue)}
        className="space-y-4"
      >
        <div className="overflow-x-auto">
          <TabsList
            variant="line"
            className="h-auto min-w-max gap-0 rounded-none border-b border-border/80 bg-transparent p-0"
          >
            {JOB_TABS.map((tab) => (
              <TabsTrigger
                key={tab.value}
                value={tab.value}
                className={JOB_TABS_TRIGGER_CLASSNAME}
              >
                {tab.label}
                <Badge
                  variant={activeTab === tab.value ? 'secondary' : 'outline'}
                  className="ml-1 h-5 px-1.5 text-[11px]"
                >
                  {tabCounts[tab.value]}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </Tabs>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search jobs"
            className="pl-9"
          />
        </div>
        <div className="flex min-h-8 items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="secondary">{visibleCount} visible</Badge>
          <Badge variant="outline">{activeTabLabel}</Badge>
        </div>
      </div>
    </>
  );
}
