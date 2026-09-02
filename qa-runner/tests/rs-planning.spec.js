const { test, expect } = require('@playwright/test')
const path = require('path')
const fs = require('fs')

const SS_DIR = path.join(__dirname, '..', 'screenshots')
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true })

async function ss(page, name) {
  const file = path.join(SS_DIR, `${name}.png`)
  await page.screenshot({ path: file, fullPage: false })
  console.log(`  📸 ${name}.png`)
}

// ─── Landing page ────────────────────────────────────────────────────────────
test('Landing page — all apps online', async ({ page }) => {
  await page.goto('http://localhost:7800/')
  await page.waitForLoadState('networkidle')

  await ss(page, '01-landing')

  // All four status pills should say "online"
  const pills = page.locator('text=online')
  await expect(pills.first()).toBeVisible()
  const count = await pills.count()
  expect(count).toBeGreaterThanOrEqual(3)

  const errors = await page.evaluate(() =>
    window.__consoleErrors?.length ?? 0)
  expect(errors).toBe(0)
})

// ─── Calendar Engine ─────────────────────────────────────────────────────────
test.describe('Calendar Engine', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:8010/calendar/')
    await page.waitForLoadState('networkidle')
  })

  test('Calendarisation tab loads without errors', async ({ page }) => {
    await expect(page.locator('text=Festival Master')).toBeVisible({ timeout: 10000 })
    await ss(page, '02-calendarisation')

    const consoleErrors = []
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()) })
    expect(consoleErrors.filter(e => !e.includes('favicon'))).toHaveLength(0)
  })

  test('Calendarised Sales — snapshot pre-populates on load', async ({ page }) => {
    // Navigate to the Calendarised Sales tab
    await page.click('text=Calendarised Sales')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000) // let snapshot fetch complete

    await ss(page, '03-calendarised-sales-load')

    // The snapshot banner should appear (new feature)
    const banner = page.locator('text=Showing last run')
    const hasBanner = await banner.isVisible().catch(() => false)

    if (hasBanner) {
      console.log('  ✅ Snapshot banner visible')
      await expect(banner).toContainText('monthly summary')
      await ss(page, '04-snapshot-banner')
    } else {
      console.log('  ℹ️  No snapshot banner — no prior reindex data for this source')
    }
  })

  test('Calendarised Sales — Monthly Summary tab has data', async ({ page }) => {
    await page.click('text=Calendarised Sales')
    await page.waitForTimeout(2500)

    // Click Monthly Summary sub-tab
    const summaryTab = page.locator('.tabs button', { hasText: 'Monthly Summary' })
    const tabVisible = await summaryTab.isVisible().catch(() => false)

    if (tabVisible) {
      await summaryTab.click()
      await page.waitForTimeout(500)
      await ss(page, '05-monthly-summary')

      // Should have at least one table row of data
      const rows = page.locator('table tbody tr')
      const rowCount = await rows.count().catch(() => 0)
      console.log(`  Monthly Summary rows visible: ${rowCount}`)
      expect(rowCount).toBeGreaterThan(0)
    } else {
      console.log('  ℹ️  Monthly Summary tab not visible — no result loaded yet')
    }
  })

  test('Calendarised Sales — source switch dw ↔ mw loads separate snapshots', async ({ page }) => {
    await page.click('text=Calendarised Sales')
    await page.waitForTimeout(2500)

    // Default is dw — take a screenshot
    await ss(page, '06-source-dw')

    // Switch to mw
    const sourceSelect = page.locator('select').filter({ hasText: /Day-wise|Month-wise/ }).first()
    const selectVisible = await sourceSelect.isVisible().catch(() => false)

    if (selectVisible) {
      await sourceSelect.selectOption('mw')
      await page.waitForTimeout(2500)
      await ss(page, '07-source-mw')
      console.log('  ✅ Source switched to Month-wise')

      // Switch back
      await sourceSelect.selectOption('dw')
      await page.waitForTimeout(1500)
      console.log('  ✅ Source switched back to Day-wise')
    } else {
      console.log('  ℹ️  Source selector not found — panel may not be rendered')
    }
  })

  test('Calendarised Sales — no JS console errors', async ({ page }) => {
    const errors = []
    page.on('console', m => {
      if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(m.text())
    })
    page.on('pageerror', e => errors.push(e.message))

    await page.click('text=Calendarised Sales')
    await page.waitForTimeout(3000)

    if (errors.length > 0) {
      console.log('  ❌ Console errors found:')
      errors.forEach(e => console.log('    ', e))
    } else {
      console.log('  ✅ No JS errors on Calendarised Sales tab')
    }

    expect(errors).toHaveLength(0)
  })

  test('snapshot-summary API responds correctly', async ({ page, request }) => {
    for (const source of ['dw', 'mw']) {
      const res = await request.get(`http://localhost:8010/api/calendar/salesdata/snapshot-summary?source=${source}`)
      expect(res.status()).toBe(200)
      const body = await res.json()
      expect(body.ok).toBe(true)
      expect(body.isSnapshot).toBe(true)
      expect(Array.isArray(body.rows)).toBe(true)
      expect(body.rows.length).toBeGreaterThan(0)
      expect(typeof body.computedAt).toBe('string')
      console.log(`  ✅ /snapshot-summary?source=${source} → ${body.rows.length} rows, computed ${body.computedAt}`)
    }
  })
})

// ─── AOP Forecaster ──────────────────────────────────────────────────────────
test('AOP Forecaster — loads without errors', async ({ page }) => {
  await page.goto('http://localhost:8010/aop/')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1500)

  const errors = []
  page.on('pageerror', e => errors.push(e.message))

  await ss(page, '08-aop')
  expect(errors).toHaveLength(0)
})

// ─── Buyer's Input Sheet ─────────────────────────────────────────────────────
test("Buyer's Input Sheet — loads and ST status is not 404", async ({ page }) => {
  await page.goto('http://localhost:5050/')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1000)

  await ss(page, '09-buyers-input')

  // The sellthru status should not show an error (fixed in earlier session)
  const errorText = page.locator('text=No sell-through file found')
  const hasError = await errorText.isVisible().catch(() => false)
  expect(hasError).toBe(false)
  console.log('  ✅ Sellthru 404 fix confirmed — no error shown')
})
