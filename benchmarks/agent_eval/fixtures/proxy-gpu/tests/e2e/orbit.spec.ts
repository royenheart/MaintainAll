import { test, expect, type Page } from '@playwright/test';
import { viewports } from '../support/viewports';
import { inspectOrbitLayout } from '../support/orbit-layout';

const url = (story: string, query = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--${story}${query}`;
async function lastCard(page: Page) {
  await page.locator('.orbit-disc').click();
  for (
    let index = 0;
    index <
    Number(await page.locator('.orbit-deck').getAttribute('data-card-count')) -
      1;
    index++
  )
    await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Next scene' })).toBeVisible();
}

test('every card fits phone, tablet, desktop, short viewports and breakpoint edges', async ({
  page,
}) => {
  await page.goto(url('still-view'));
  await expect(page.getByRole('article')).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  test.setTimeout(120000);
  const sizes = [
    ...viewports,
    ...[638, 639, 640, 641].map((width) => ({ width, height: 600 })),
  ];
  for (const viewport of sizes) {
    await page.setViewportSize(viewport);
    for (
      let index = 0;
      index <
      Number(await page.locator('.orbit-deck').getAttribute('data-card-count'));
      index++
    ) {
      await expect
        .poll(() => page.evaluate(inspectOrbitLayout), {
          message: `${viewport.width}x${viewport.height}, card ${index + 1}`,
        })
        .toEqual([]);
      if (
        index <
        Number(
          await page.locator('.orbit-deck').getAttribute('data-card-count'),
        ) -
          1
      ) {
        await page
          .getByRole('button', { name: 'Next card', exact: true })
          .click();
        await expect(page.getByRole('article')).toHaveAttribute(
          'aria-label',
          [
            'Inside this scene',
            'On the turntable',
            'Blog',
            'GitHub',
            'Beyond this scene',
          ][index]!,
        );
      }
    }
    for (
      let index = 0;
      index <
      Number(
        await page.locator('.orbit-deck').getAttribute('data-card-count'),
      ) -
        1;
      index++
    )
      await page.getByRole('button', { name: 'Previous card' }).click();
    await expect(
      page.getByRole('article', { name: 'A little about me' }),
    ).toBeVisible();
  }
});

test('Tab opens the wheel, Escape restores focus, and scrolling is scoped to the deck', async ({
  page,
}) => {
  await page.goto(url('still-view'));
  await page.locator('.orbit-disc').click();
  await expect(
    page.getByRole('region', { name: 'Information cards' }),
  ).toHaveCount(0);
  await page
    .locator('.orbit-disc')
    .evaluate((node) => (node as HTMLButtonElement).blur());
  await page.keyboard.press('Tab');
  // Tab order can continue after the previous focused element; start from the document.
  await page.evaluate(() => {
    (document.activeElement as HTMLElement)?.blur();
    document.body.tabIndex = -1;
    document.body.focus();
  });
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('region', { name: 'Information cards' }),
  ).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('.orbit-disc')).toBeFocused();
  await expect(
    page.getByRole('region', { name: 'Information cards' }),
  ).toHaveCount(0);
  await page.locator('.orbit-disc').click();
  await page.mouse.move(100, 100);
  await page.mouse.wheel(0, 500);
  await expect(
    page.getByRole('article', { name: 'A little about me' }),
  ).toBeVisible();
  await page.locator('.orbit-card-front').hover();
  await page.mouse.wheel(0, 300);
  await expect(
    page.getByRole('article', { name: 'Inside this scene' }),
  ).toBeVisible();
});

test('repeated navigation advances once, resizes in flight, and reverses the same geometry', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto(url('cubes-open', '&capture=1'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  for (
    let index = 0;
    index <
    Number(await page.locator('.orbit-deck').getAttribute('data-card-count')) -
      1;
    index++
  )
    await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await page.getByRole('button', { name: 'Next scene' }).evaluate((node) => {
    for (let index = 0; index < 15; index++)
      (node as HTMLButtonElement).click();
  });
  await expect(page.locator('main')).toHaveAttribute(
    'data-transitioning',
    'true',
  );
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.blend))
    .toBeGreaterThan(0.2);
  await page.setViewportSize({ width: 390, height: 400 });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
  await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  await lastCard(page);
  await page.getByRole('button', { name: 'Previous scene' }).click();
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.blend))
    .toBeLessThan(0.8);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes');
  await expect(page.locator('main')).toHaveAttribute(
    'data-transitioning',
    'false',
  );
  expect(errors).toEqual([]);
});

test('real audio drives the ring and completion; quiet entry has no automatic scene timer', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        const scope = window as unknown as { testAudio: HTMLAudioElement[] };
        (scope.testAudio ??= []).push(this);
      }
    };
  });
  await page.goto(url('still-view'));
  await expect(page.locator('main')).toHaveAttribute(
    'data-audio-ready',
    'true',
  );
  await page.locator('.orbit-disc').click();
  await page.getByRole('button', { name: 'Play music', exact: true }).click();
  await expect
    .poll(() =>
      page.locator('.orbit-spectrum').getAttribute('data-energy').then(Number),
    )
    .toBeGreaterThan(0);
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-energy',
    '0',
  );
  await page.getByRole('button', { name: 'Play music', exact: true }).click();
  await page.evaluate(() => {
    (window as unknown as { testAudio: HTMLAudioElement[] }).testAudio.find(
      (audio) => !audio.paused,
    )!.currentTime = 11.85;
  });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'true',
  );
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await page.waitForTimeout(13000);
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
});

test('reduced motion rests the renderer and graphics failure retains navigation', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(url('cubes-open'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  await page.waitForTimeout(200);
  const frames = await page.evaluate(() => window.__orbitScene?.frames);
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__orbitScene?.frames)).toBe(frames);
  await page
    .locator('canvas')
    .evaluate((node) =>
      node.dispatchEvent(new Event('webglcontextlost', { cancelable: true })),
    );
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Blog' })).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
});
