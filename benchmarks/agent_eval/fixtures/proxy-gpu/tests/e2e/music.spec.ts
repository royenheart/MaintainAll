import { test, expect } from '@playwright/test';

test('track changes and reopen own their timers while an old embed is pending', async ({
  page,
}) => {
  let releaseOld = () => {};
  let oldRequested = false;
  const pendingOld = new Promise<void>((resolve) => {
    releaseOld = resolve;
  });
  await page.route('https://music.163.com/**', async (route) => {
    if (new URL(route.request().url()).searchParams.get('id') === '111') {
      oldRequested = true;
      await pendingOld;
    }
    await route.fulfill({
      contentType: 'text/html',
      body: '<button>Play fixture</button>',
    });
  });
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=music-panel--multiple-tracks&viewMode=story',
  );
  await expect(page.getByRole('button', { name: 'Listen' })).toBeVisible();
  await page.clock.install();
  await page.clock.pauseAt(new Date(Date.now() + 100));
  await page.getByRole('button', { name: 'Listen' }).click();
  const oldFrame = await page.locator('iframe').elementHandle();
  await expect.poll(() => oldRequested).toBe(true);
  await page.clock.runFor(500);
  await page
    .getByRole('combobox', { name: 'Choose a track' })
    .selectOption('second');
  releaseOld();
  expect(await oldFrame!.evaluate((element) => element.isConnected)).toBe(
    false,
  );
  await expect(page.locator('iframe')).toHaveCount(1);
  await expect(page.locator('iframe')).toHaveAttribute('src', /id=222/);
  await page.clock.runFor(600);
  await expect(page.getByRole('status')).toHaveText(
    'Playback is provided by NetEase. Press play in the player.',
  );
  await page.clock.runFor(500);
  await expect(page.getByRole('status')).toContainText(
    'If the player is unavailable',
  );
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(page.locator('iframe')).toHaveCount(0);
  await page.getByRole('button', { name: 'Listen' }).click();
  await expect(page.getByRole('status')).toContainText(
    'Playback is provided by NetEase',
  );
  await page.keyboard.press('Escape');
  await page.clock.runFor(1200);
  await expect(page.getByRole('button', { name: 'Listen' })).toBeFocused();
  await expect(page.getByRole('status')).toHaveCount(0);
});

test('narrow music does not load an iframe and resizing cleans up the player', async ({
  page,
}) => {
  let embedRequests = 0;
  await page.route('https://music.163.com/**', (route) => {
    embedRequests++;
    return route.fulfill({ contentType: 'text/html', body: 'Player fixture' });
  });
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('/original/?graphics=poster');
  await page.getByRole('button', { name: 'Listen' }).click();
  await expect(
    page.getByRole('link', { name: 'Open track', exact: true }),
  ).toBeVisible();
  await expect(page.locator('iframe')).toHaveCount(0);
  expect(embedRequests).toBe(0);
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.locator('iframe')).toHaveCount(1);
  await page.setViewportSize({ width: 320, height: 568 });
  await expect(page.locator('iframe')).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Open track', exact: true }),
  ).toBeVisible();
});
