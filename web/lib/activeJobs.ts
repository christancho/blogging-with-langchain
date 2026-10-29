'use client';

import { createContext, useContext } from 'react';
import type { Job } from '@/lib/api';

export interface ActiveJobs {
  jobs: Job[];
  /** True until the first snapshot arrives. */
  loading: boolean;
}

/** Pending/running jobs from the dashboard layout's single /jobs/stream subscription. */
export const ActiveJobsContext = createContext<ActiveJobs | null>(null);

export function useActiveJobs(): ActiveJobs {
  const ctx = useContext(ActiveJobsContext);
  if (!ctx) throw new Error('useActiveJobs must be used inside the dashboard layout');
  return ctx;
}
