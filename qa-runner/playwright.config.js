const { defineConfig } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:8010',
    storageState: './auth/state.json',
    headless: false,
    channel: 'msedge',
    viewport: { width: 1400, height: 900 },
    screenshot: 'only-on-failure',
    video: 'off',
    // Slower actions so you can watch what's happening on screen
    actionTimeout: 10000,
  },
  reporter: [
    ['list'],
    ['html', { outputFolder: 'report', open: 'never' }],
  ],
  // Run tests sequentially so the browser is easy to follow on screen
  workers: 1,
})
