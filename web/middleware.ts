import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('access_token')?.value;

  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  // Decode JWT payload (no signature verification — backend validates on each request)
  try {
    const [, payloadB64] = token.split('.');
    const payload = JSON.parse(
      Buffer.from(payloadB64, 'base64url').toString('utf-8')
    );
    if (payload.exp && Date.now() / 1000 > payload.exp) {
      const response = NextResponse.redirect(new URL('/login', request.url));
      response.cookies.delete('access_token');
      return response;
    }
  } catch {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Protect all dashboard routes; leave /login and /api/webhook/* open
  matcher: ['/queue', '/new-post', '/history/:path*', '/settings'],
};
