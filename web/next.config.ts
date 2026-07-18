import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Pin Turbopack's workspace root to this app directory. Otherwise Next walks
  // up the tree looking for a lockfile and can latch onto a stray one (e.g.
  // ~/package-lock.json), inferring the wrong workspace root.
  // https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
