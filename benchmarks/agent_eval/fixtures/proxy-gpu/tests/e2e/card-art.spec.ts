import { expect, test } from '@playwright/test';
import { inspectSlotCard } from '../support/slot-layout';

for (const art of ['engraving', 'foil', 'relief']) {
  test(`${art} preserves card attachment and readable content in both scenes`, async ({
    page,
  }) => {
    test.setTimeout(60000);
    await page.route('**/song/media/outer/**', (route) => route.abort());
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?card=elsewhere&cardArt=${art}&scene=${scene}&graphics=poster&skipIntro=1`,
      );
      for (const viewport of [
        { width: 320, height: 320 },
        { width: 390, height: 844 },
        { width: 768, height: 1024 },
        { width: 1440, height: 900 },
      ]) {
        await page.mouse.move(4, 4);
        await page.setViewportSize(viewport);
        const button = page.getByRole('button', { name: 'Blog', exact: true });
        await button.hover();
        const card = page.getByRole('group', { name: 'Current card' });
        await expect(card).toHaveAttribute('data-state', 'open');
        await expect(card.locator('.scene-card-art')).toHaveAttribute(
          'data-art',
          art,
        );
        await expect(card.locator('.scene-card-art')).toHaveAttribute(
          'data-scene',
          scene,
        );
        await expect(card).toHaveAttribute('data-material', 'drift');
        await expect(page.locator('.slot-card-aperture')).toHaveAttribute(
          'data-extraction',
          'slide',
        );
        await expect(button.locator('.orbit-dock-icon')).toHaveCount(0);
        await expect(button.locator('.elsewhere-miniature')).toBeVisible();
        await expect.poll(() => page.evaluate(inspectSlotCard)).toEqual([]);
        expect(
          await card.evaluate((el) => el.scrollWidth - el.clientWidth),
        ).toBeLessThanOrEqual(1);
        const overflows = await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        );
        expect(overflows).toBe(false);
        await page.keyboard.press('Escape');
        await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
      }
    }
  });
}

test('music source glyph rotates without moving its target, border, or native tooltip', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto('/preview/?scene=cubes&graphics=poster&skipIntro=1');
  const deck = page.getByRole('region', { name: 'Information slots' });
  await deck.focus();
  await page.keyboard.press('ArrowDown');
  await expect(deck).toHaveAttribute('data-moving', 'false');
  const source = page
    .locator('.rotary-card-active .orbit-source-links a')
    .first();
  const glyph = source.locator('svg');
  const bounds = await source.boundingBox();
  await glyph.evaluate((el) => {
    const samples: number[] = [];
    (window as unknown as { sourceTurns: number[] }).sourceTurns = samples;
    const start = performance.now();
    const sample = () => {
      samples.push(
        Number(el.style.transform.match(/rotate\(([-\d.]+)deg\)/)?.[1] ?? 0),
      );
      if (performance.now() - start < 1200) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
  await source.hover();
  await expect
    .poll(() =>
      glyph.evaluate((el) => {
        return Number(
          el.style.transform.match(/rotate\(([-\d.]+)deg\)/)?.[1] ?? 0,
        );
      }),
    )
    .toBe(360);
  const turns = await page.evaluate(
    () => (window as unknown as { sourceTurns: number[] }).sourceTurns,
  );
  expect(turns.some((degrees) => degrees > 90 && degrees < 270)).toBe(true);
  expect(new Set(turns.map(Math.round)).size).toBeGreaterThan(6);
  expect(await source.boundingBox()).toEqual(bounds);
  await expect(source).toHaveCSS('box-shadow', 'none');
  await expect(
    page.locator('.rotary-deck button[title], .rotary-deck a[title]'),
  ).toHaveCount(0);
  await page.mouse.move(4, 4);
  await expect
    .poll(() =>
      glyph.evaluate(
        (el) =>
          Math.abs(new DOMMatrixReadOnly(getComputedStyle(el).transform).b) <
          0.00001,
      ),
    )
    .toBe(true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.keyboard.press('Tab');
  await source.focus();
  await source.hover();
  await expect(glyph).toHaveCSS('transform', 'none');
  await expect(source).not.toHaveCSS('outline-style', 'none');
});
