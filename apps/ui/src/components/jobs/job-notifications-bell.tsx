'use client';

import { Bell, CircleAlert, CircleCheck, MessageSquare } from 'lucide-react';

import { useJobDetail } from '@/components/jobs/job-detail-context';
import {
  useJobNotifications,
  type JobNotificationStatus,
} from '@/components/jobs/job-notifications-context';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { formatRelativeTime } from '@/lib/job-formatters';

function NotificationIcon({ status }: { status: JobNotificationStatus }) {
  if (status === 'failed') {
    return <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />;
  }
  if (status === 'waiting') {
    return (
      <MessageSquare className="mt-0.5 size-4 shrink-0 text-amber-500 dark:text-amber-400" />
    );
  }
  return (
    <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
  );
}

export function JobNotificationsBell() {
  const { notifications, unreadCount, markAllRead, clear } =
    useJobNotifications();
  const { openJobDetail } = useJobDetail();

  return (
    <Popover
      onOpenChange={(open) => {
        if (open) markAllRead();
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-8 w-8"
          aria-label={
            unreadCount > 0
              ? `Notifications, ${unreadCount} unread`
              : 'Notifications'
          }
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium leading-none text-primary-foreground">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-medium">Notifications</span>
          {notifications.length > 0 ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={clear}
            >
              Clear
            </Button>
          ) : null}
        </div>
        {notifications.length === 0 ? (
          <div className="px-3 py-8 text-center text-sm text-muted-foreground">
            No notifications yet.
          </div>
        ) : (
          <ul className="max-h-80 divide-y divide-border/70 overflow-y-auto">
            {notifications.map((notification) => (
              <li key={notification.id}>
                <button
                  type="button"
                  onClick={() => openJobDetail(notification.jobId)}
                  className="flex w-full gap-2.5 px-3 py-2.5 text-left transition hover:bg-muted/50"
                >
                  <NotificationIcon status={notification.status} />
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">
                        {notification.jobName}
                      </span>
                      <span className="shrink-0 text-[11px] text-muted-foreground">
                        {formatRelativeTime(notification.at)}
                      </span>
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {notification.summary}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
