import { test, expect } from '@playwright/test';
import { viewports } from '../support/viewports';
import { inspectLayout } from '../support/layout';

for (const viewport of viewports) {
  test(`page geometry: ${viewport.name} ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto('/original/?graphics=poster');
    await expect(
      page.getByRole('button', { name: 'Switch scene' }),
    ).toBeVisible();
    await expect
      .poll(async () => (await page.evaluate(inspectLayout)).issues)
      .toEqual([]);
    await page.getByRole('button', { name: 'Switch scene' }).click();
    await expect(page.locator('.scene-experience')).toHaveAttribute(
      'data-scene',
      'horizon',
    );
    await expect
      .poll(async () => (await page.evaluate(inspectLayout)).issues)
      .toEqual([]);
  });
}

test('geometry checks detect real overlap and clipping defects', async ({
  page,
}) => {
  await page.goto('/original/?graphics=poster');
  await page.locator('[data-layout="legal"]').evaluate((element) => {
    (element as HTMLElement).style.cssText =
      'position:absolute;left:0;top:0;width:200vw';
  });
  const report = await page.evaluate(inspectLayout);
  expect(report.issues).toContain('Legal links escapes its container');
  expect(report.issues).toContain('Document overflows horizontally');
  await page.evaluate(() => {
    const music = document
      .querySelector('[data-layout="music"]')!
      .getBoundingClientRect();
    const legal = document.querySelector<HTMLElement>('[data-layout="legal"]')!;
    legal.style.cssText = `position:fixed;left:${music.x}px;top:${music.y}px;width:${music.width}px;height:${music.height}px`;
  });
  expect((await page.evaluate(inspectLayout)).issues).toContain(
    'Music and legal links overlap',
  );
  await page.locator('[data-layout="legal"]').evaluate((element) => {
    element.removeAttribute('style');
  });
  await page.locator('[data-layout="scene"]').evaluate((element) => {
    (element as HTMLElement).style.transform = 'translateX(8px)';
  });
  expect((await page.evaluate(inspectLayout)).issues).toContain(
    'Desktop navigation and scene are misaligned',
  );
});

test('layout survives a resize during repeated scene changes', async ({
  page,
}) => {
  await page.goto('/original/?graphics=poster');
  for (const viewport of [...viewports.slice(3, 9), viewports[0]!]) {
    await page.getByRole('button', { name: 'Switch scene' }).click();
    await page.setViewportSize(viewport);
    await expect
      .poll(async () => (await page.evaluate(inspectLayout)).issues)
      .toEqual([]);
  }
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-scene',
    'horizon',
  );
});

test('keyboard, narrow music fallback, and 200 percent text size remain usable', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto('/original/?graphics=poster');
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  await page.getByRole('button', { name: 'Listen' }).click();
  await expect(
    page.getByRole('link', { name: 'Open track', exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Listen' })).toBeFocused();
  await expect
    .poll(async () => (await page.evaluate(inspectLayout)).issues)
    .toEqual([]);
});

test('static HTML preserves navigation without JavaScript', async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:4321/original/');
  await expect(
    page.getByRole('link', { name: 'Blog', exact: true }),
  ).toHaveAttribute('href', 'https://royenheart.github.io');
  await expect(page.locator('.scene-poster')).toBeVisible();
  await expect(page.locator('.track-name')).toHaveAttribute('href', /30953026/);
  await context.close();
});

test('touch input works at phone and tablet device pixel ratios', async ({
  browser,
  browserName,
}) => {
  test.skip(
    browserName === 'firefox',
    'Playwright Firefox does not support isMobile contexts.',
  );
  for (const device of [
    { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 },
    { viewport: { width: 768, height: 1024 }, deviceScaleFactor: 2 },
  ]) {
    const context = await browser.newContext({
      ...device,
      isMobile: true,
      hasTouch: true,
    });
    try {
      const page = await context.newPage();
      await page.goto('http://127.0.0.1:4321/original/?graphics=poster');
      await page.getByRole('button', { name: 'Switch scene' }).tap();
      await expect(page.locator('.scene-experience')).toHaveAttribute(
        'data-scene',
        'horizon',
      );
      await page.getByRole('button', { name: 'Listen' }).tap();
      await expect(
        page.getByRole('region', { name: 'NetEase player' }),
      ).toBeVisible();
      await page.getByRole('button', { name: 'Close', exact: true }).tap();
      await expect
        .poll(async () => (await page.evaluate(inspectLayout)).issues)
        .toEqual([]);
    } finally {
      await context.close();
    }
  }
});
