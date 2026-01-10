import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Test Configuration
 * 
 * Tests cover:
 * - Reachability audit (R-01, R-02)
 * - UX audit (понятность и "без тупиков")
 * - Compatibility audit (браузеры/устройства)
 */

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results.json' }],
  ],
  
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  /* Configure projects for major browsers */
  projects: [
    // C-01: Chrome
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // C-01: Firefox  
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    // C-01: Safari
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // C-02: Mobile Chrome (если нужно)
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    // C-02: Mobile Safari
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  /* Run your local dev server before starting the tests */
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});

