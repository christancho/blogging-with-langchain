'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { auth, jobs, type Job } from '@/lib/api';

const NAV_ITEMS = [
  {
    href: '/new-post',
    label: 'New Post',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
  {
    href: '/queue',
    label: 'Queue',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
      </svg>
    ),
  },
  {
    href: '/history',
    label: 'History',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    href: '/settings',
    label: 'Settings',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [queueCount, setQueueCount] = useState(0);

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

  function isActive(href: string) {
    if (href === '/history') return pathname.startsWith('/history');
    return pathname === href;
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="h-14 flex items-center px-5 border-b border-gray-100">
          <span className="text-sm font-semibold text-gray-900 tracking-tight">Blog Generator</span>
        </div>

        <nav className="flex-1 py-3 px-2 space-y-0.5">
          {NAV_ITEMS.map(item => (
            <Link
              key={item.href}
              href={item.href}
              className={`relative flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive(item.href)
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              {item.icon}
              {item.label}
              {item.href === '/queue' && queueCount > 0 && (
                <span className="ml-auto bg-blue-600 text-white text-xs rounded-full h-5 min-w-5 px-1 flex items-center justify-center">
                  {queueCount > 9 ? '9+' : queueCount}
                </span>
              )}
            </Link>
          ))}
        </nav>

        <div className="px-2 py-3 border-t border-gray-100">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto px-6 py-6">
          {children}
        </div>
      </main>
    </div>
  );
}
