'use client';

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react';

const MAX_NOTIFICATIONS = 30;

export type JobNotificationStatus = 'waiting' | 'failed' | 'success';

export interface JobNotification {
  /** Stable per-run id (matches the toast id) used for de-duplication. */
  id: string;
  jobId: string;
  jobName: string;
  status: JobNotificationStatus;
  summary: string;
  /** ISO timestamp of the run event. */
  at: string;
  read: boolean;
}

interface JobNotificationsValue {
  notifications: JobNotification[];
  unreadCount: number;
  addNotification: (notification: Omit<JobNotification, 'read'>) => void;
  markAllRead: () => void;
  clear: () => void;
}

const JobNotificationsContext = createContext<JobNotificationsValue | null>(
  null,
);

export function useJobNotifications(): JobNotificationsValue {
  const ctx = useContext(JobNotificationsContext);
  if (!ctx) {
    throw new Error(
      'useJobNotifications must be used inside JobNotificationsProvider',
    );
  }
  return ctx;
}

export function JobNotificationsProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [notifications, setNotifications] = useState<JobNotification[]>([]);

  const addNotification = useCallback(
    (notification: Omit<JobNotification, 'read'>) => {
      setNotifications((prev) => {
        if (prev.some((entry) => entry.id === notification.id)) {
          return prev;
        }
        return [{ ...notification, read: false }, ...prev].slice(
          0,
          MAX_NOTIFICATIONS,
        );
      });
    },
    [],
  );

  const markAllRead = useCallback(() => {
    setNotifications((prev) =>
      prev.some((entry) => !entry.read)
        ? prev.map((entry) => (entry.read ? entry : { ...entry, read: true }))
        : prev,
    );
  }, []);

  const clear = useCallback(() => setNotifications([]), []);

  const unreadCount = useMemo(
    () =>
      notifications.reduce((count, entry) => count + (entry.read ? 0 : 1), 0),
    [notifications],
  );

  const value = useMemo(
    () => ({ notifications, unreadCount, addNotification, markAllRead, clear }),
    [notifications, unreadCount, addNotification, markAllRead, clear],
  );

  return (
    <JobNotificationsContext.Provider value={value}>
      {children}
    </JobNotificationsContext.Provider>
  );
}
