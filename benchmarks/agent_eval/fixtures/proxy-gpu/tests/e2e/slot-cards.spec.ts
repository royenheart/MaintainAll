import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';
import { inspectSlotCard } from '../support/slot-layout';

for (const motion of ['slide', 'lift', 'fan']) {
  test(`${motion} extracts bound cards, returns old content and honors the last intent`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    await page.goto(
      `/preview/?card=elsewhere&cardMotion=${motion}&graphics=poster&skipIntro=1`,
    );
    const deck = page.getByRole('region', { name: 'Information slots' });
    await expect(deck).toHaveAttribute('data-moving', 'false');
    await expect(page.locator('.rotary-card[data-bound-cards]')).toHaveCount(1);
    await expect(page.locator('.slot-card-stack i')).toHaveCount(2);
    const blog = page.getByRole('button', { name: 'Blog', exact: true });
    const github = page.getByRole('button', { name: 'GitHub', exact: true });
    const icon = blog.locator('.orbit-segment-label');
    await expect
      .poll(() =>
        page
          .locator('.orbit-dock')
          .evaluate(
            (el) => new DOMMatrixReadOnly(getComputedStyle(el).transform).m42,
          ),
      )
      .toBe(0);
    const resting = await icon.boundingBox();
    await blog.hover();
    const tip = page.getByRole('group', { name: 'Current card' });
    await expect(tip).toHaveAttribute('data-state', 'open');
    expect(await icon.boundingBox()).toEqual(resting);
    await page.mouse.down();
    expect(await icon.boundingBox()).toEqual(resting);
    await page.mouse.move(4, 4);
    await page.mouse.up();
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    await blog.hover();
    await expect(tip).toHaveAttribute('data-state', 'open');
    await page.evaluate(() => {
      const root = document.querySelector('.slot-card-portals')!;
      (window as unknown as { cardExits: string[] }).cardExits = [];
      new MutationObserver(() => {
        root.querySelectorAll('[data-state="returning"]').forEach((card) => {
          (window as unknown as { cardExits: string[] }).cardExits.push(
            card.textContent ?? '',
          );
        });
      }).observe(root, { attributes: true, subtree: true, childList: true });
    });
    await github.hover();
    await expect(tip).toContainText('@royenheart');
    await expect(tip).toHaveAttribute('data-state', 'open');
    expect(
      await page.evaluate(() =>
        (window as unknown as { cardExits: string[] }).cardExits.some((text) =>
          text.includes('Blog'),
        ),
      ),
    ).toBe(true);
    await expect(page.locator('.slot-card-aperture')).toHaveCount(1);
    await expect(tip).not.toContainText('github.com');
    await blog.hover();
    await github.hover();
    await blog.hover();
    await expect(tip).toContainText('Blog');
    await expect(tip).toHaveAttribute('data-state', 'open');
    await tip.hover();
    await expect(tip).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    await github.hover();
    await page.keyboard.press('Escape');
    await blog.hover();
    await expect(tip).toContainText('Blog');
    await expect(tip).toHaveAttribute('data-state', 'open');
    await page.setViewportSize({ width: 390, height: 400 });
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    await deck.focus();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await expect(github).toBeFocused();
    await expect(tip).toHaveAttribute('data-state', 'open');
    await deck.press('End');
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await deck.press('ArrowUp');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await blog.focus();
    await expect(tip).toHaveAttribute('data-state', 'open');
    await expect(tip).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)');
    await expect(tip.locator('.slot-card-material i').first()).toHaveCSS(
      'animation-name',
      'none',
    );
    await expect.poll(() => page.evaluate(inspectSlotCard)).toEqual([]);
    const insertedBottom = await tip.evaluate((el) => el.style.bottom);
    await tip.evaluate(
      (el) => (el.style.bottom = `${parseFloat(el.style.bottom) + 24}px`),
    );
    expect(await page.evaluate(inspectSlotCard)).toContain(
      'Card detached from its source lip',
    );
    await tip.evaluate(
      (el, value) => (el.style.bottom = value),
      insertedBottom,
    );
    await expect.poll(() => page.evaluate(inspectSlotCard)).toEqual([]);
    // The containment oracle must reject a genuinely overflowing card.
    const contained = () =>
      tip.evaluate((el) => {
        const r = el.getBoundingClientRect();
        return r.left >= 0 && r.right <= innerWidth && r.top >= 0;
      });
    expect(await contained()).toBe(true);
    await tip.evaluate((el) => (el.style.width = '800px'));
    expect(await contained()).toBe(false);
    await tip.evaluate((el) => el.style.removeProperty('width'));
    expect(await contained()).toBe(true);
  });
}

for (const material of ['drift', 'light', 'layers']) {
  test(`${material} animates only the card material and closes on visibility loss`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    await page.goto(
      `/preview/?card=elsewhere&cardSurface=${material}&graphics=poster&skipIntro=1`,
    );
    await page.getByRole('button', { name: 'GitHub', exact: true }).hover();
    const tip = page.getByRole('group', { name: 'Current card' });
    await expect(tip).toHaveAttribute('data-state', 'open');
    const content = tip.locator('.slot-card-content');
    const box = await content.boundingBox();
    const layer = tip.locator('.slot-card-material i').first();
    const initial = await layer.evaluate(
      (el) => getComputedStyle(el).transform,
    );
    await expect
      .poll(() => layer.evaluate((el) => getComputedStyle(el).transform))
      .not.toBe(initial);
    expect(await content.boundingBox()).toEqual(box);
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'hidden',
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
  });
}
