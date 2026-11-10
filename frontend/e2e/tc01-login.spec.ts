import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-01: Valid login opens the dashboard', () => {
  test('entering correct credentials logs in and shows the dashboard', async ({ page }) => {
    // Do NOT inject token — start unauthenticated so login page shows
    await setupApiMocks(page, { authenticated: false });
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Should see the login page
    await expect(page.locator('h1')).toContainText('Sign in to IntelliRoads', { timeout: 10_000 });

    // Fill in valid credentials
    await page.fill('#username', 'admin');
    await page.fill('#password', 'admin123');
    await page.click('button[type="submit"]');

    // After login, the dashboard should appear — Header h1 says "Overview"
    await expect(page.locator('h1').first()).toContainText('Overview', { timeout: 15_000 });

    // Token should be stored in localStorage
    const token = await page.evaluate(() => localStorage.getItem('intelliroads_token'));
    expect(token).toBe('mock-valid-e2e-token-xyz');
  });
});
