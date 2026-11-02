import { expect, test } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const fixture = fileURLToPath(
  new URL(
    '../../src/explorations/audio-fixtures/steady-tone.mp3',
    import.meta.url,
  ),
);

test('random artwork treatment is chosen once per accepted scene transition', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto('/preview/?scene=cubes&graphics=poster');
  await expect(page.locator('main')).toHaveAttribute('data-font', 'plex');
  await expect(page.locator('main')).toHaveAttribute(
    'data-cover-selection',
    'random',
  );
  const deck = page.locator('.rotary-deck');
  const choices = [
    [0.01, 'ripple'],
    [0.5, 'frost'],
    [0.99, 'meniscus'],
  ] as const;
  for (const [random, effect] of choices) {
    await deck.press('End');
    await page.evaluate((value) => {
      Math.random = () => value;
    }, random);
    await page
      .getByRole('button', {
        name: effect === 'frost' ? 'Previous scene' : 'Next scene',
        exact: true,
      })
      .evaluate((button) => {
        (button as HTMLButtonElement).click();
        Math.random = () => 0.25;
        (button as HTMLButtonElement).click();
      });
    await expect(page.locator('.orbit-cover-transition')).toHaveAttribute(
      'data-effect',
      effect,
    );
    await expect(page.locator('main')).toHaveAttribute(
      'data-transitioning',
      'false',
    );
    await expect(deck).toHaveAttribute('data-card-index', '0');
    await page.setViewportSize({
      width: effect === 'frost' ? 390 : 800,
      height: 600,
    });
    await expect(page.locator('.orbit-cover-transition')).toHaveAttribute(
      'data-effect',
      effect,
    );
  }
});

test('three cover treatments share a scrubbed phase without overflow and respect reduced motion', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1320, height: 860 });
  await page.goto('/preview-covers/');
  const slider = page.getByRole('slider', { name: 'Transition progress' });
  await slider.fill('0.5');
  await expect(page.locator('feDisplacementMap').first()).toHaveAttribute(
    'scale',
    '11',
  );
  await expect(page.locator('[data-effect=ripple] .cover-material')).toHaveCSS(
    'filter',
    /url.*blur/,
  );
  await expect(page.locator('[data-effect=frost] .cover-material')).toHaveCSS(
    'filter',
    'blur(7px)',
  );
  await expect(
    page.locator('[data-effect=meniscus] [data-cover=horizon]'),
  ).toHaveCSS('clip-path', /ellipse/);
  for (const size of [
    { width: 1320, height: 860 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const boxes = await page
      .locator('.cover-lab-sample')
      .evaluateAll((nodes) =>
        nodes.map((node) => node.getBoundingClientRect().toJSON()),
      );
    for (let i = 1; i < boxes.length; i++) {
      const a = boxes[i - 1]!;
      const b = boxes[i]!;
      expect(b.x >= a.right || b.y >= a.bottom).toBe(true);
    }
  }
  await page.getByRole('button', { name: 'To horizon' }).click();
  await page.getByRole('button', { name: 'To Axolotl' }).click();
  await expect
    .poll(async () => Number(await slider.inputValue()))
    .toBeLessThan(0.4);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await slider.fill('0.5');
  await expect(page.locator('[data-effect=ripple] .cover-material')).toHaveCSS(
    'filter',
    'none',
  );
});

test('automatic entry chooses either scene on reload without a gate and keeps cards visible', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    Math.random = () => Number(sessionStorage.getItem('test-random') ?? 0.1);
  });
  await page.goto('/preview/?graphics=poster');
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes');
  await expect(page.locator('.rotary-card-active')).toHaveAttribute(
    'aria-label',
    'RoyenHeart on Axolotl',
  );
  await expect(page.locator('.orbit-arrival, .orbit-scene-number')).toHaveCount(
    0,
  );
  await page.locator('.rotary-deck').press('Escape');
  await expect(page.locator('.rotary-deck')).toBeVisible();
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await expect(page.locator('.rotary-deck')).toBeVisible();
  await page.locator('.rotary-deck').press('ArrowDown');
  await expect(
    page.getByRole('navigation', { name: 'Music platforms' }),
  ).toBeVisible();
  await page.locator('.rotary-deck').press('ArrowDown');
  await expect(
    page.getByRole('navigation', { name: 'Elsewhere' }).getByRole('link'),
  ).toHaveCount(2);
  await page.evaluate(() => sessionStorage.setItem('test-random', '0.9'));
  await page.reload();
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
  await expect(page.locator('.rotary-card-active')).toHaveAttribute(
    'aria-label',
    'RoyenHeart on Event horizon',
  );
  await expect(page.locator('.rotary-deck')).toHaveAttribute(
    'data-card-count',
    '4',
  );
});

test('denied autoplay does not gate visuals, and native playback drives clearly moving cube bars', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) =>
    route.fulfill({ path: fixture, contentType: 'audio/mpeg' }),
  );
  await page.addInitScript(() => {
    const scope = window as unknown as {
      allowSound: boolean;
      attempts: number;
      decks: HTMLAudioElement[];
    };
    scope.allowSound = false;
    scope.attempts = 0;
    scope.decks = [];
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor() {
        super();
        this.loop = true;
        scope.decks.push(this);
      }
    };
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
      scope.attempts++;
      return scope.allowSound
        ? play.call(this)
        : Promise.reject(
            new DOMException('Blocked autoplay', 'NotAllowedError'),
          );
    };
  });
  await page.goto('/preview/?scene=cubes&graphics=poster');
  await expect(page.locator('.rotary-deck')).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => (window as unknown as { attempts: number }).attempts),
    )
    .toBe(1);
  await page.evaluate(() => {
    (window as unknown as { allowSound: boolean }).allowSound = true;
  });
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Play music', exact: true }).click();
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'ambient',
  );
  const lengths = () =>
    page
      .locator('.orbit-spectrum line')
      .evaluateAll((nodes) =>
        nodes.map((node) => Number(node.getAttribute('y2'))),
      );
  const first = await lengths();
  await expect
    .poll(async () =>
      Math.max(
        ...(await lengths()).map((value, index) =>
          Math.abs(value - first[index]!),
        ),
      ),
    )
    .toBeGreaterThan(2);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as unknown as { decks: HTMLAudioElement[] }).decks[0]!
            .currentTime,
      ),
    )
    .toBeGreaterThan(0.3);
  await expect(page.locator('.orbit-spectrum line').first()).toHaveCSS(
    'opacity',
    '0.84',
  );
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'rest',
  );
  await expect.poll(lengths).toEqual(Array(64).fill(12));
});

test('cover materials remain mounted through rapid navigation, resize and failed artwork', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.route('**/9xUrtBaorkUdSUGQozuldA==/**', (route) => route.abort());
  for (const cover of ['ripple', 'frost', 'meniscus']) {
    await page.goto(`/preview/?scene=cubes&graphics=poster&cover=${cover}`);
    const deck = page.locator('.rotary-deck');
    await expect(deck).toBeVisible();
    await page.locator('.cover-material').evaluate((node) => {
      node.setAttribute('data-original', 'true');
    });
    await deck.press('End');
    await page
      .getByRole('button', { name: 'Next scene', exact: true })
      .evaluate((button) => {
        (button as HTMLButtonElement).click();
        (button as HTMLButtonElement).click();
      });
    await expect(deck).toBeVisible();
    await page.setViewportSize({ width: 390, height: 400 });
    await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
    await expect(page.locator('main')).toHaveAttribute(
      'data-transitioning',
      'false',
    );
    await expect(
      page.locator('.cover-material[data-original=true]'),
    ).toHaveCount(1);
    await expect(
      page.locator(
        '.cover-layer[data-cover=horizon] .orbit-artwork-placeholder',
      ),
    ).toBeVisible();
    await expect(deck).toHaveAttribute('data-card-index', '0');
    await expect(deck).toBeFocused();
    await deck.press('End');
    await page
      .getByRole('button', { name: 'Previous scene', exact: true })
      .click();
    await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes');
    await expect(page.locator('.cover-material')).toHaveCSS('filter', 'none');
  }
});
