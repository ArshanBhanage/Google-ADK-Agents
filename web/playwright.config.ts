import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:5173' },
  webServer: [
    { command: '../.venv/bin/uvicorn api.main:app --app-dir .. --host 127.0.0.1 --port 8000 --no-access-log', url: 'http://127.0.0.1:8000/api/health', reuseExistingServer: false },
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
  ],
});
