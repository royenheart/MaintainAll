import { test, expect } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';

test('selected soundtracks keep every ribbon behind the artwork during forward and reverse exchanges', async ({
  page,
}) => {
  test.setTimeout(120000);
  // Playback availability is independent of this geometry and motion contract.
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const scene of ['cubes', 'horizon']) {
    for (const viewport of [
      { width: 320, height: 568 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto(
        `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-${scene}&args=skipEntrance:true;startOpen:true;graphics:poster;dockDesign:classic`,
      );
      await expect(page.locator('main')).toHaveAttribute(
        'data-dock-design',
        'classic',
      );
      await expect(page.getByRole('article')).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => {
        const state = { frames: 0, issues: new Set<string>(), running: true };
        Object.assign(window, { ribbonAudit: state });
        const sample = () => {
          if (!state.running) return;
          state.frames++;
          const cover = document
            .querySelector('.orbit-artwork')!
            .getBoundingClientRect();
          const cx = cover.x + cover.width / 2;
          const cy = cover.y + cover.height / 2;
          for (const card of document.querySelectorAll('.orbit-card')) {
            const style = getComputedStyle(card);
            if (Number(style.opacity) < 0.05) continue;
            const r = card.getBoundingClientRect();
            if (r.top < cover.top - 1 || r.bottom > cover.bottom + 1)
              state.issues.add('Moving ribbon escapes the artwork height');
            const x = r.right - 1,
              y = r.top + 1;
            if (Math.hypot(x - cx, y - cy) > cover.width / 2)
              state.issues.add('Moving upper seam escapes the artwork circle');
            if (!document.elementFromPoint(x, y)?.closest('.orbit-disc'))
              state.issues.add(
                'Moving upper seam is not covered by the artwork',
              );
          }
          requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
      });
      const count = Number(
        await page.locator('.orbit-deck').getAttribute('data-card-count'),
      );
      expect(count).toBe(8);
      for (const direction of ['Next card', 'Previous card']) {
        for (let index = 1; index < count; index++) {
          const previous = await page
            .getByRole('article')
            .getAttribute('aria-label');
          await page
            .getByRole('button', { name: direction, exact: true })
            .click();
          await expect(page.getByRole('article')).not.toHaveAttribute(
            'aria-label',
            previous!,
          );
          await expect
            .poll(() => page.evaluate(inspectOrbitLayout))
            .toEqual([]);
        }
      }
      const result = await page.evaluate(() => {
        const audit = (
          window as unknown as {
            ribbonAudit: {
              frames: number;
              issues: Set<string>;
              running: boolean;
            };
          }
        ).ribbonAudit;
        audit.running = false;
        return { frames: audit.frames, issues: [...audit.issues] };
      });
      expect(result.frames).toBeGreaterThan(20);
      expect(
        result.issues,
        `${scene}, ${viewport.width}x${viewport.height}`,
      ).toEqual([]);
    }
  }
});
