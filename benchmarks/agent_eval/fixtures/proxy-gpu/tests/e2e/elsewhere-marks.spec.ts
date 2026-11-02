import { expect, test } from '@playwright/test';
import { inspectSlotCard } from '../support/slot-layout';

for (const mark of ['emblem', 'intaglio', 'editorial']) {
  test(`${mark} keeps semantic marks and straight, recessed cards usable in both scenes`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    for (const [scene, art] of [
      ['horizon', 'relief'],
      ['cubes', 'foil'],
    ]) {
      await page.goto(
        `/preview/?scene=${scene}&marks=${mark}&card=elsewhere&skipIntro=1&graphics=poster`,
      );
      for (const size of [
        { width: 320, height: 400 },
        { width: 1440, height: 900 },
      ]) {
        await page.mouse.move(4, 4);
        await page.setViewportSize(size);
        const blog = page.getByRole('button', { name: 'Blog', exact: true });
        const github = page.getByRole('button', {
          name: 'GitHub',
          exact: true,
        });
        await expect(blog.locator('.elsewhere-mark')).toHaveAttribute(
          'data-kind',
          'blog',
        );
        await expect(github.locator('.elsewhere-mark')).toHaveAttribute(
          'data-kind',
          'github',
        );
        await expect(github.locator('.elsewhere-mark')).toHaveAttribute(
          'data-mark',
          mark,
        );
        const stack = page.locator('.slot-card-stack');
        await expect(stack).toHaveCSS('opacity', '0.2');
        const inset = await stack.evaluate(
          (el) =>
            el.getBoundingClientRect().left -
            el.closest('.rotary-card')!.getBoundingClientRect().left,
        );
        expect(inset).toBeCloseTo(32, 1);
        await blog.hover();
        const card = page.getByRole('group', { name: 'Current card' });
        await expect(card).toHaveAttribute('data-state', 'open');
        await expect(card.locator('.scene-card-art')).toHaveAttribute(
          'data-art',
          art!,
        );
        await expect(page.locator('.slot-card-aperture')).toHaveAttribute(
          'data-extraction',
          'slide',
        );
        await expect(card).toHaveCSS('opacity', '1');
        await expect.poll(() => page.evaluate(inspectSlotCard)).toEqual([]);
        await github.hover();
        await expect(card).toContainText('GitHub');
        await expect(card).toHaveAttribute('data-state', 'open');
        await expect(card.locator('[data-icon="github"]')).toBeVisible();
        await page.keyboard.press('Escape');
        await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
      }
    }
  });
}
