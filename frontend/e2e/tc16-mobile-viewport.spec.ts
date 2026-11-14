import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

const ROUTES_TO_TEST = ['/', '/details', '/map', '/analytics', '/alerts', '/reports', '/settings'];

test.describe('TC-16: Mobile viewport (390px) responsiveness', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true });
  });

  for (const path of ROUTES_TO_TEST) {
    test(`route "${path}" has no horizontal overflow at 390px width`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1000);

      // Verify that scrollWidth does not exceed clientWidth (no horizontal scrollbar on root/body)
      const overflow = await page.evaluate(() => {
        const docEl = document.documentElement;
        const body = document.body;
        const scrollWidth = Math.max(docEl.scrollWidth, body.scrollWidth);
        const clientWidth = docEl.clientWidth;
        return {
          hasOverflow: scrollWidth > clientWidth,
          scrollWidth,
          clientWidth,
        };
      });

      expect(overflow.hasOverflow).toBe(false);
    });
  }
});
