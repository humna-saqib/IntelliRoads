import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

const ROUTES = ['/', '/details', '/map', '/analytics', '/alerts', '/reports', '/settings'];

test.describe('Accessibility & Responsive Proof Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true });
  });

  test('Skip link is the first tab stop and focuses main content on activation', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);

    // Press Tab once to bring focus to the skip-to-content link
    await page.keyboard.press('Tab');
    const skipLink = page.locator('a[href="#main-content"]');
    await expect(skipLink).toBeFocused();

    // Activating the skip link moves focus to main#main-content
    await page.keyboard.press('Enter');
    const mainContent = page.locator('main#main-content');
    await expect(mainContent).toBeFocused();
  });

  test('Tab order reaches main actions on Home page', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);

    // Collect focused accessible elements as user tabs through the interface
    const focusedLabels: string[] = [];
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press('Tab');
      const info = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el) return null;
        return el.getAttribute('aria-label') || el.textContent?.trim() || el.tagName.toLowerCase();
      });
      if (info) focusedLabels.push(info);
    }

    // Verify key actions are in the tab sequence
    const joined = focusedLabels.join(' | ');
    expect(joined).toContain('Skip to main content');
    // Main actions on Home (Glossary, Tour, or Timing Switch)
    const hasHomeAction = focusedLabels.some(
      (label) =>
        label.includes('Glossary') ||
        label.includes('Tour') ||
        label.includes('Standard timing') ||
        label.includes('Smart AI'),
    );
    expect(hasHomeAction).toBe(true);
  });

  test('Each authenticated route has exactly one h1 heading', async ({ page }) => {
    for (const route of ROUTES) {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(400);

      const h1Count = await page.locator('h1').count();
      expect(h1Count, `Route ${route} should have exactly one h1 heading`).toBe(1);
    }
  });

  test('Login page has exactly one h1 heading', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('intelliroads_token');
    });
    await setupApiMocks(page, { authenticated: false });
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(400);

    const h1Count = await page.locator('h1').count();
    expect(h1Count, 'Login page should have exactly one h1 heading').toBe(1);
    await expect(page.locator('h1')).toHaveText(/Sign in to IntelliRoads/i);
  });
});

test.describe('Tablet viewport (768px) responsiveness', () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true });
  });

  for (const path of ROUTES) {
    test(`route "${path}" has no horizontal overflow at 768px tablet width`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(600);

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

      expect(overflow.hasOverflow, `Route ${path} has horizontal scrollbar at 768px (scrollWidth: ${overflow.scrollWidth}, clientWidth: ${overflow.clientWidth})`).toBe(false);
    });
  }
});
