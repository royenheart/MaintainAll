import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

const fixture = fileURLToPath(
  new URL(
    '../../src/explorations/audio-fixtures/steady-tone.mp3',
    import.meta.url,
  ),
);

test('selected nameplate reserves the playing response and keeps one card reflection', async ({
  page,
}) => {
  test.setTimeout(90000);
  const bytes = await readFile(fixture);
  await page.route('**/song/media/outer/**', (route) => {
    // WebKit requests byte ranges when a looping MP3 seeks back to its start.
    const range = route
      .request()
      .headers()
      .range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2]
      ? Math.min(Number(range[2]), bytes.length - 1)
      : bytes.length - 1;
    return route.fulfill({
      status: range ? 206 : 200,
      contentType: 'audio/mpeg',
      headers: {
        'Accept-Ranges': 'bytes',
        ...(range
          ? { 'Content-Range': `bytes ${start}-${end}/${bytes.length}` }
          : {}),
      },
      body: bytes.subarray(start, end + 1),
    });
  });
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        this.muted = true;
        this.loop = true;
      }
    };
  });
  for (const scene of ['cubes', 'horizon']) {
    await page.goto(`/preview/?scene=${scene}&graphics=poster&skipIntro=1`);
    await expect(page.locator('main')).toHaveAttribute(
      'data-card-finish',
      'nameplate',
    );
    await expect(page.locator('main')).toHaveAttribute(
      'data-surface-motion',
      'drift',
    );
    const deck = page.locator('.rotary-deck');
    await deck.press('End');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    const play = page.getByRole('button', { name: 'Play music', exact: true });
    if (await play.isVisible()) await play.click();
    await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
      'data-response',
      'ambient',
    );
    for (const size of [
      { width: 320, height: 320 },
      { width: 390, height: 844 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(size);
      await deck.press('Home');
      for (let card = 0; card < 4; card++) {
        await expect(deck).toHaveAttribute('data-moving', 'false');
        await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
        await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
        const clearance = await page.evaluate(() => {
          const ink = [
            ...document.querySelectorAll(
              '.orbit-spectrum line, .orbit-spectrum path',
            ),
          ];
          const content = [
            ...document.querySelectorAll(
              '.rotary-card-active a, .rotary-card-active button, .rotary-card-active .orbit-ribbon-copy',
            ),
          ];
          return (
            Math.min(...ink.map((el) => el.getBoundingClientRect().left)) -
            Math.max(
              ...content
                .map((el) => el.getBoundingClientRect())
                .filter((r) => r.width)
                .map((r) => r.right),
            )
          );
        });
        expect(clearance).toBeGreaterThan(8);
        if (card < 3) await deck.press('ArrowDown');
      }
    }
    // Deliberately restore the previous insufficient inset to validate the oracle.
    await deck.evaluate((el) =>
      el.style.setProperty(
        '--card-pad-right',
        'calc(var(--orbit-wheel) * .38 + 12px)',
      ),
    );
    await expect
      .poll(() => page.evaluate(inspectRotaryLayout))
      .toContain('Card content enters the audio response clearance');
    await deck.evaluate((el) => el.style.removeProperty('--card-pad-right'));
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await page.mouse.click(5, 5);
    const reflection = page.locator('.rotary-card-active .finish-reflection');
    await expect(reflection).toHaveCSS('opacity', '0');
    const controls = page.locator('.orbit-transport button');
    const backgrounds = await controls.evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node, '::before').background),
    );
    for (let index = 0; index < 3; index++) {
      await controls.nth(index).hover();
      expect(
        await controls
          .nth(index)
          .evaluate((node) => getComputedStyle(node, '::after').display),
      ).toBe('none');
    }
    await expect(reflection).toHaveCSS('opacity', '1');
    for (let index = 0; index < 4; index++) await controls.nth(1).click();
    expect(
      await controls.evaluateAll((nodes) =>
        nodes.map((node) => getComputedStyle(node, '::before').background),
      ),
    ).toEqual(backgrounds);
    // Moving between controls does not restart the card-wide sweep.
    await expect
      .poll(() =>
        reflection.evaluate((node) => getComputedStyle(node).transform),
      )
      .toBe('matrix(1, 0, 0, 1, 710, 0)');
    await controls.nth(0).hover();
    await expect(reflection).toHaveCSS(
      'transform',
      'matrix(1, 0, 0, 1, 710, 0)',
    );
    await page.mouse.click(5, 5);
    await expect(reflection).toHaveCSS('opacity', '0');
  }
});

for (const surface of ['drift', 'layers', 'light']) {
  test(`${surface} advances only the active material and respects motion preference`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    await page.goto(
      `/preview/?surface=${surface}&scene=horizon&graphics=poster&skipIntro=1`,
    );
    const deck = page.locator('.rotary-deck');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    const moving = page.locator(
      `.rotary-card-active .${surface === 'light' ? 'finish-light-field' : 'finish-enamel-field'}`,
    );
    const start = await moving.evaluate(
      (node) => getComputedStyle(node).transform,
    );
    await expect
      .poll(() => moving.evaluate((node) => getComputedStyle(node).transform))
      .not.toBe(start);
    await expect(moving).toHaveCSS('animation-play-state', 'running');
    expect(
      await page
        .locator(
          '.rotary-card:not(.rotary-card-active) .finish-material-motion',
        )
        .evaluateAll((nodes) =>
          nodes.every(
            (node) => getComputedStyle(node).animationPlayState === 'paused',
          ),
        ),
    ).toBe(true);
    await deck.press('ArrowDown');
    await expect(deck).toHaveAttribute('data-moving', 'true');
    await expect(moving).toHaveCSS('animation-play-state', 'paused');
    await deck.press('ArrowUp');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    await expect(moving).toHaveCSS('animation-play-state', 'running');
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'hidden',
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(moving).toHaveCSS('animation-play-state', 'paused');
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'visible',
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(moving).toHaveCSS('animation-play-state', 'running');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(moving).toHaveCSS('animation-name', 'none');
    await expect(moving).toHaveCSS('transform', 'none');
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
  });
}
