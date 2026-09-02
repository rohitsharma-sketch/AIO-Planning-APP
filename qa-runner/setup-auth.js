/**
 * One-time setup: opens a Playwright Chromium window so you can log in,
 * then auto-saves your session once it detects you're on the Calendar page.
 * No Enter needed — just log in and it saves automatically.
 *
 * Usage: node setup-auth.js
 */
const { chromium } = require('playwright')
const path = require('path')
const fs = require('fs')

async function main() {
  const statePath = path.join(__dirname, 'auth', 'state.json')
  const authDir = path.join(__dirname, 'auth')
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true })

  console.log('\nOpening Chromium — log in to the app...\n')

  // Use system Edge (already on Windows 11 — no download, no AV issues)
  const browser = await chromium.launch({
    headless: false,
    channel: 'msedge',
    args: ['--start-maximized'],
  })

  const context = await browser.newContext({ viewport: null })
  const page = await context.newPage()
  await page.goto('http://localhost:8010/calendar/')

  console.log('Waiting for you to log in...')
  console.log('(The window will close automatically once you are on the Calendar page)\n')

  // Wait until we're past the login page — detect either the tab nav
  // or the URL moving away from /login
  await page.waitForFunction(() => {
    // Logged in = the main Calendar nav tabs are visible
    const tabs = document.querySelectorAll('nav a, .tab, [role="tab"]')
    const tabTexts = [...tabs].map(t => t.textContent || '')
    const hasCalendarNav = tabTexts.some(t => t.includes('Calendarisation') || t.includes('Version'))
    // Also accept if URL is not /login
    const notOnLogin = !window.location.pathname.includes('login')
    return hasCalendarNav || notOnLogin
  }, {}, { timeout: 120000, polling: 1000 })

  // Small pause to let the page finish loading
  await page.waitForTimeout(1500)

  await context.storageState({ path: statePath })
  console.log(`\nSession saved to auth/state.json`)
  console.log('Closing Chromium...\n')
  await browser.close()
  console.log('Done! Run: npx playwright test\n')
}

main().catch(e => { console.error('\nSetup failed:', e.message); process.exit(1) })
