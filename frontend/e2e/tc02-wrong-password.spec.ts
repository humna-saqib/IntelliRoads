import { test, expect } from '@playwright/test';
import { setupApiMocks } from './mocks/setupMocks';

test.describe('TC-02: Wrong password shows error and prevents access', () => {
  test('wrong credentials show error message and do not store a token', async ({ page }) => {
    // Start unauthenticated
    await setupApiMocks(page, { authenticated: false });
    await page.goto('/', { waitUntil: 'domcontentloaded' });

    // Should see the login page
    await expect(page.locator('h1')).toContainText('Sign in to IntelliRoads', { timeout: 10_000 });

    // Fill in wrong credentials (postData containing "wrong" triggers 401 in mock)
    await page.fill('#username', 'admin');
    await page.fill('#password', 'wrong');
    await page.click('button[type="submit"]');

    // Should see a friendly error message
    await expect(page.locator('[role="alert"]')).toContainText(
      'Wrong username or password',
      { timeout: 10_000 },
    );

    // Should still be on the login page — no token stored
    const token = await page.evaluate(() => localStorage.getItem('intelliroads_token'));
    expect(token).toBeNull();

    // Should still show the login form (not the dashboard)
    await expect(page.locator('h1')).toContainText('Sign in to IntelliRoads');
  });
});
