import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-15: Dark mode is remembered after reload', () => {
  test('switching theme toggles dark class and choice persists across reload', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_tour_completed', 'true');
    });
    await setupApiMocks(page, { authenticated: true });

    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Locate the ThemeToggle button by matching either dark or light label
    const themeBtn = page.getByRole('button', { name: /Switch to (dark|light) theme/i });
    await expect(themeBtn).toBeVisible({ timeout: 10_000 });

    // Read the current theme state
    const isInitiallyDark = await page.locator('html').evaluate((el) => el.classList.contains('dark'));

    // Click the toggle button to switch theme
    await themeBtn.click();

    // The dark class state should now be flipped
    if (isInitiallyDark) {
      await expect(page.locator('html')).not.toHaveClass(/dark/, { timeout: 5_000 });
      const stored = await page.evaluate(() => localStorage.getItem('intelliroads_theme'));
      expect(stored).toBe('light');

      // Reload and verify persisted
      await page.reload({ waitUntil: 'domcontentloaded' });
      await expect(page.locator('html')).not.toHaveClass(/dark/, { timeout: 10_000 });
      const storedAfter = await page.evaluate(() => localStorage.getItem('intelliroads_theme'));
      expect(storedAfter).toBe('light');
    } else {
      await expect(page.locator('html')).toHaveClass(/dark/, { timeout: 5_000 });
      const stored = await page.evaluate(() => localStorage.getItem('intelliroads_theme'));
      expect(stored).toBe('dark');

      // Reload and verify persisted
      await page.reload({ waitUntil: 'domcontentloaded' });
      await expect(page.locator('html')).toHaveClass(/dark/, { timeout: 10_000 });
      const storedAfter = await page.evaluate(() => localStorage.getItem('intelliroads_theme'));
      expect(storedAfter).toBe('dark');
    }
  });
});
