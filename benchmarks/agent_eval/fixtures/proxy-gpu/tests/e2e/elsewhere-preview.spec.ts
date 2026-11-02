import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';
import { inspectSlotCard } from '../support/slot-layout';

for (const study of ['glyph', 'index', 'tile']) {
  test(`${study} discloses attached cards with stable targets and unobscured text`, async ({
    page,
  }) => {
    test.setTimeout(60000);
    await page.route('**/song/media/outer/**', (route) => route.abort());
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?elsewhere=${study}&scene=${scene}&card=elsewhere&graphics=poster&skipIntro=1`,
      );
      const deck = page.locator('.rotary-deck');
      const blog = page.getByRole('button', { name: 'Blog', exact: true });
      const github = page.getByRole('button', { name: 'GitHub', exact: true });
      await expect(blog).toHaveText('');
      await expect(github).toHaveText('');
      for (const size of [
        { width: 320, height: 320 },
        { width: 390, height: 844 },
        { width: 1440, height: 900 },
      ]) {
        await page.mouse.move(4, 4);
        await page.setViewportSize(size);
        await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
        await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
        await expect
          .poll(() =>
            page
              .locator('.orbit-dock')
              .evaluate(
                (el) =>
                  new DOMMatrixReadOnly(getComputedStyle(el).transform).m42,
              ),
          )
          .toBe(0);
        const hit = await blog.boundingBox();
        await blog.hover();
        const card = page.getByRole('group', { name: 'Current card' });
        await expect(card).toHaveAttribute('data-state', 'open');
        await expect(card).toContainText('Blog');
        await expect(card).not.toContainText('royenheart.github.io');
        await expect(
          card.getByRole('link', { name: 'Open Blog' }),
        ).toHaveAttribute('href', 'https://royenheart.github.io');
        await expect.poll(() => page.evaluate(inspectSlotCard)).toEqual([]);
        expect(await blog.boundingBox()).toEqual(hit);
        await card.hover();
        await expect(card).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
        await deck.focus();
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await expect(github).toBeFocused();
        await expect(card).toContainText('@royenheart');
        if (study !== 'glyph')
          await expect(card).toContainText('Fly Me To The Moon');
        await page.keyboard.press('Escape');
        await expect(card).toHaveCount(0);
        await expect(github).toBeFocused();
        await page.mouse.click(4, 4);
      }
      await blog.hover();
      await github.hover();
      await blog.hover();
      await expect(
        page.getByRole('group', { name: 'Current card' }),
      ).toContainText('Blog');
      await page.setViewportSize({ width: 390, height: 600 });
      await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
      await github.click();
      await expect(
        page.getByRole('group', { name: 'Current card' }),
      ).toBeVisible();
      await deck.press('End');
      await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    }
  });
}

test('touch selects a card and its native action opens the destination', async ({
  browser,
}) => {
  const context = await browser.newContext({
    hasTouch: true,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto('/preview/?card=elsewhere&graphics=poster&skipIntro=1');
  const blog = page.getByRole('button', { name: 'Blog', exact: true });
  const url = page.url();
  await blog.tap();
  const card = page.getByRole('group', { name: 'Current card' });
  await expect(card).toHaveAttribute('data-state', 'open');
  expect(page.url()).toBe(url);
  await blog.tap();
  expect(page.url()).toBe(url);
  await page.route('https://royenheart.github.io/', (route) =>
    route.fulfill({
      body: '<h1>Destination fixture</h1>',
      contentType: 'text/html',
    }),
  );
  await page.getByRole('link', { name: 'Open Blog' }).tap();
  await expect(page).toHaveURL('https://royenheart.github.io/');
  await context.close();
});

test('short-card content scrolls before the inner deck advances and never turns the outer deck', async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 240 });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto('/preview/?card=elsewhere&graphics=poster&skipIntro=1');
  await page.getByRole('button', { name: 'Blog', exact: true }).click();
  const card = page.getByRole('group', { name: 'Current card' });
  await expect(card).toHaveAttribute('data-state', 'open');
  await card.hover();
  await page.mouse.wheel(0, 25);
  await expect
    .poll(() => card.evaluate((el) => el.scrollTop))
    .toBeGreaterThan(0);
  await expect(page.locator('.rotary-card-active')).toHaveAttribute(
    'data-card-id',
    'elsewhere',
  );
  await expect(
    page.getByRole('region', { name: 'Elsewhere cards' }),
  ).toHaveAttribute('data-card-index', '0');
});
