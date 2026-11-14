import type { Page, Route } from '@playwright/test';
import * as mockData from './trafficData';

export interface MockOptions {
  authenticated?: boolean;
  controllerMode?: 'RULE_BASED' | 'DQN';
  simulateOffline?: boolean;
}

/**
 * Sets up Playwright route interception for all API requests and WebSocket connections.
 * Ensures tests run completely offline and deterministically.
 *
 * API paths match those in frontend/src/services/api.ts (BASE_URL = '/api').
 */
export async function setupApiMocks(page: Page, options: MockOptions = {}) {
  const { authenticated = true, simulateOffline = false } = options;
  let activeMode = options.controllerMode || 'RULE_BASED';

  // Inject authentication token if authenticated is true
  if (authenticated) {
    await page.addInitScript(() => {
      localStorage.setItem('intelliroads_token', 'mock-valid-e2e-token-xyz');
    });
  }

  // If simulateOffline is true, fail all API requests with network error
  if (simulateOffline) {
    await page.route('**/api/**', (route: Route) => {
      route.abort('failed');
    });
    return;
  }

  // Intercept all /api/ calls
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    // 1. Auth Login — api.ts uses POST /api/auth/login
    if (path === '/api/auth/login' && method === 'POST') {
      const postData = route.request().postData() || '';
      if (postData.includes('wrong') || postData.includes('invalid')) {
        return route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Incorrect username or password' }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_LOGIN_SUCCESS),
      });
    }

    // 2. Intersections
    if (path === '/api/intersections') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_INTERSECTIONS),
      });
    }

    // 3. KPIs
    if (path === '/api/kpis') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_KPIS),
      });
    }

    // 4. Signals
    if (path === '/api/signals') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_SIGNALS),
      });
    }

    // 5. Density
    if (path === '/api/density') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_DENSITY),
      });
    }

    // 6. Occupancy
    if (path === '/api/occupancy') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_OCCUPANCY),
      });
    }

    // 7. Emergency
    if (path === '/api/emergency') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_EMERGENCY),
      });
    }

    // 8. Controller Mode — api.ts uses /api/rl/mode (GET and POST)
    if (path === '/api/rl/mode') {
      if (method === 'POST') {
        const json = route.request().postDataJSON() || {};
        activeMode = json.mode || 'DQN';
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'ok', mode: activeMode }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...mockData.MOCK_CONTROLLER_MODE, mode: activeMode }),
      });
    }

    // 9. Active RL model — api.ts uses /api/rl/model
    if (path === '/api/rl/model') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          model: 'dqn_obs_v2',
          mode: activeMode,
          file: 'checkpoint_ep200.pth',
          obs_version: 'obs-v2',
        }),
      });
    }

    // 10. Vehicles
    if (path === '/api/vehicles') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_VEHICLES),
      });
    }

    // 11. Classification
    if (path === '/api/classification') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_CLASSIFICATION),
      });
    }

    // 12. Congestion — /api/congestion/resolve, /api/congestion/history, /api/congestion
    if (path === '/api/congestion/resolve' && method === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'resolved' }),
      });
    }
    if (path === '/api/congestion/history') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_CONGESTION_HISTORY),
      });
    }
    if (path === '/api/congestion') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_CONGESTION),
      });
    }

    // 13. Performance
    if (path === '/api/performance/history') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_PERFORMANCE_HISTORY),
      });
    }
    if (path === '/api/performance') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_PERFORMANCE),
      });
    }

    // 14. Density history
    if (path === '/api/density/history') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockData.MOCK_DENSITY_HISTORY),
      });
    }

    // 15. Settings/Thresholds — api.ts uses /api/settings/thresholds
    if (path.startsWith('/api/settings/thresholds')) {
      if (method === 'PUT') {
        const body = route.request().postDataJSON() || {};
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(body),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          junctionA: mockData.MOCK_SETTINGS,
          junctionB: mockData.MOCK_SETTINGS,
          junctionC: mockData.MOCK_SETTINGS,
          junctionD: mockData.MOCK_SETTINGS,
        }),
      });
    }

    // Fallback for any other API route — return empty success
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok' }),
    });
  });

  // Handle WebSocket — close so the app falls back to REST polling
  if ('routeWebSocket' in page) {
    try {
      await (page as any).routeWebSocket(/ws/, (ws: any) => {
        ws.close();
      });
    } catch {
      // routeWebSocket may not be available on all environments
    }
  }
}
