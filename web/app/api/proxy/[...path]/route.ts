import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.API_URL ?? 'http://localhost:8000';

async function handler(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${API_URL}/${path.join('/')}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  headers.delete('host');

  const body = req.method === 'GET' || req.method === 'HEAD'
    ? undefined
    : await req.arrayBuffer();

  const res = await fetch(url, {
    method: req.method,
    headers,
    body: body ? Buffer.from(body) : undefined,
  });

  const resHeaders = new Headers(res.headers);
  resHeaders.delete('transfer-encoding');

  return new NextResponse(await res.arrayBuffer(), {
    status: res.status,
    headers: resHeaders,
  });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
