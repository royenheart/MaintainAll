import { test, expect } from '@playwright/test';
import { viewports } from '../support/viewports';
import { inspectLayout } from '../support/layout';

test('Storybook pages pass the full width and height matrix', async ({
  page,
}, testInfo) => {
  await page.route('https://music.163.com/**', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<button>Play fixture</button>',
    }),
  );
  for (const story of ['desktop', 'empty-playlist', 'long-track']) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=page-home-frame--${story}&viewMode=story`,
    );
    await expect(page.locator('.home-frame')).toBeVisible();
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect
        .poll(async () => (await page.evaluate(inspectLayout)).issues, {
          message: `${story} at ${viewport.width}x${viewport.height}`,
        })
        .toEqual([]);
    }
  }
  await page.screenshot({
    path: testInfo.outputPath('storybook-layout.png'),
    fullPage: true,
  });
});

test('Storybook scene controls withstand interrupted interactions and resizing', async ({
  page,
}) => {
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=page-home-frame--desktop&viewMode=story',
  );
  const button = page.getByRole('button', { name: 'Switch scene' });
  await expect(button).toBeVisible();
  const before = await page
    .locator('.scene-experience')
    .getAttribute('data-scene');
  await button.evaluate((element) => {
    for (let i = 0; i < 21; i++) (element as HTMLButtonElement).click();
  });
  await page.setViewportSize({ width: 390, height: 400 });
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-scene',
    before === 'cubes' ? 'horizon' : 'cubes',
  );
  await expect
    .poll(async () => (await page.evaluate(inspectLayout)).issues)
    .toEqual([]);
});
