// Isolated verification only: same-origin requests reach the synthetic API.
import { defineConfig, mergeConfig } from 'vite';
import base from './vite.config';

export default mergeConfig(
  base,
  defineConfig({
    server: { allowedHosts: ['frontend-verify'], proxy: { '/api': 'http://api:8000' } },
  }),
);
