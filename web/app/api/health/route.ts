import { NextResponse } from 'next/server';

const API_URL = process.env.API_URL ?? 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const res = await fetch(`${API_URL}/health`, { cache: 'no-store' });
    if (!res.ok) {
      console.error(`Health check: API returned ${res.status}`);
      return NextResponse.json({ status: 'degraded', api: 'unhealthy' }, { status: 503 });
    }
    return NextResponse.json({ status: 'ok' });
  } catch (err) {
    console.error('Health check: API unreachable', err);
    return NextResponse.json({ status: 'degraded', api: 'unreachable' }, { status: 503 });
  }
}
