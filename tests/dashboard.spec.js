// @ts-check
const { test, expect } = require('@playwright/test');

test('dashboard loads without console errors', async ({ page }) => {
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(err.message));

  await page.goto('/');
  await expect(page.locator('h1')).toContainText('OpenTelemetry Rust');
  expect(consoleErrors).toEqual([]);
});

test('sparkline canvases are present in cards', async ({ page }) => {
  await page.goto('/');

  const canvasIds = [
    'chart-issues-open',
    'chart-triage-30d',
    'chart-triage-1y',
    'chart-prs-open',
    'chart-prs-merged',
    'chart-first-review',
    'chart-time-merge',
  ];

  for (const id of canvasIds) {
    await expect(page.locator(`#${id}`)).toBeAttached();
  }
});

test('all sparklines have Chart.js instances with data', async ({ page }) => {
  await page.goto('/');
  await page.waitForFunction(() => typeof Chart !== 'undefined');

  const canvasIds = [
    'chart-issues-open',
    'chart-triage-30d',
    'chart-triage-1y',
    'chart-prs-open',
    'chart-prs-merged',
    'chart-first-review',
    'chart-time-merge',
  ];

  const results = await page.evaluate((ids) => {
    return ids.map(id => {
      const canvas = document.getElementById(id);
      if (!canvas) return { id, hasChart: false, dataPoints: 0 };
      const chart = Chart.getChart(canvas);
      return {
        id,
        hasChart: !!chart,
        dataPoints: chart ? chart.data.labels.length : 0,
      };
    });
  }, canvasIds);

  for (const result of results) {
    expect(result.hasChart, `${result.id} should have a Chart.js instance`).toBe(true);
    expect(result.dataPoints, `${result.id} should have trend data`).toBeGreaterThan(0);
  }
});
