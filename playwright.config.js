// @ts-check
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:4173',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npx serve site -l 4173',
    port: 4173,
    reuseExistingServer: false,
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
