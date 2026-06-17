/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Necessário para o Dockerfile multi-stage copiar apenas o standalone output
  output: 'standalone',
};

module.exports = nextConfig;