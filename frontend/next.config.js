const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Register the `@/*` path alias in webpack directly.
  // This is more reliable than relying on tsconfig's `paths` field during
  // production builds, which has bitten us in Docker before.
  webpack: (config) => {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.join(__dirname, 'src'),
    };
    config.resolve.fallback = { ...config.resolve.fallback, fs: false };
    return config;
  },

  // Server-side proxy for /api/* → backend.
  // IMPORTANT: use a NON-public env var here. `NEXT_PUBLIC_*` gets baked into
  // the JS bundle at build time, but rewrites are evaluated at server startup,
  // so we want a separate variable that's read fresh when the Next.js server
  // boots inside the container.
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
