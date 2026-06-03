'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { auth, jobs, type Job } from '@/lib/api';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [queueCount, setQueueCount] = useState(0);

  // Poll queue badge every 3s
  useEffect(() => {
    let cancelled = false;
    async function fetchCount() {
      try {
        const all: Job[] = await jobs.list();
        if (!cancelled) {
          setQueueCount(all.filter(j => j.status === 'pending' || j.status === 'running').length);
        }
      } catch (err: unknown) {
        if ((err as { status?: number }).status === 401) {
          router.push('/login');
        }
      }
    }
    fetchCount();
    const interval = setInterval(fetchCount, 3000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [router]);

  async function handleLogout() {
    await auth.logout().catch(() => {});
    router.push('/login');
  }

  const tabs = [
    { href: '/new-post', label: 'New Post' },
    { href: '/queue', label: 'Queue' },
    { href: '/history', label: 'History' },
    { href: '/settings', label: 'Settings' },
  ];

  function isActive(href: string) {
    if (href === '/history') return pathname.startsWith('/history');
    return pathname === href;
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="bg-white border-b border-gray-200 px-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between h-14">
          <div className="flex gap-1">
            {tabs.map(tab => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`relative px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                  isActive(tab.href)
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                }`}
              >
                {tab.label}
                {tab.href === '/queue' && queueCount > 0 && (
                  <span className="absolute -top-1 -right-1 bg-blue-600 text-white text-xs rounded-full h-4 w-4 flex items-center justify-center">
                    {queueCount > 9 ? '9+' : queueCount}
                  </span>
                )}
              </Link>
            ))}
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Sign out
          </button>
        </div>
      </nav>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        {children}
      </main>
    </div>
  );
}
