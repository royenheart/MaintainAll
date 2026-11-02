import { test, expect } from '@playwright/test';
import { viewports } from '../support/viewports';
import { inspectConceptLayout } from '../support/concept-layout';

const directions = [
  'orbital-console',
  'liquid-chrome',
  'quiet-gallery',
  'pop-circuit',
];

test('native audio obeys play, seek, rapid pause, next, previous and track end', async ({
  page,
}) => {
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=music-unified-player--local-audio',
  );
  const audio = page.locator('audio');
  await page.getByRole('button', { name: 'Play music' }).click();
  await expect(page.locator('.unified-player')).toHaveAttribute(
    'data-playing',
    'true',
  );
  await expect
    .poll(() =>
      audio.evaluate((node) => (node as HTMLAudioElement).currentTime),
    )
    .toBeGreaterThan(0);
  await expect(
    page.getByRole('slider', { name: 'Track position' }),
  ).toBeEnabled();
  await page.getByRole('slider', { name: 'Track position' }).click();
  await expect(
    page.getByRole('slider', { name: 'Track position' }),
  ).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.getByText('Golden Orbit')).toBeVisible();
  await expect
    .poll(() => audio.evaluate((node) => !(node as HTMLAudioElement).paused))
    .toBe(true);
  await page.getByRole('button', { name: 'Previous track' }).click();
  await expect(page.getByText('Blue Hour')).toBeVisible();
  await page.getByRole('button', { name: 'Pause music' }).click();
  for (let i = 0; i < 4; i++) {
    await page.getByRole('button', { name: 'Play music' }).click();
    await page.getByRole('button', { name: 'Pause music' }).click();
  }
  await expect
    .poll(() => audio.evaluate((node) => (node as HTMLAudioElement).paused))
    .toBe(true);
  await expect(page.locator('.unified-player')).toHaveAttribute(
    'data-playing',
    'false',
  );
  await page.getByRole('button', { name: 'Next track' }).click();
  await expect(page.getByText('Golden Orbit')).toBeVisible();
  await expect
    .poll(() => audio.evaluate((node) => (node as HTMLAudioElement).paused))
    .toBe(true);
  await expect(audio).toHaveCount(1);
  await expect(page.locator('iframe')).toHaveCount(0);
});
for (const direction of directions) {
  test(`${direction} retains geometry across widths, heights and interrupted input`, async ({
    page,
  }) => {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=explorations-design-directions--${direction}&viewMode=story&graphics=poster`,
    );
    await expect(page.locator('.design-concept')).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect
        .poll(() => page.evaluate(inspectConceptLayout), {
          message: `${direction}: ${viewport.width}x${viewport.height}`,
        })
        .toEqual([]);
    }
    await page
      .getByRole('button', { name: 'Switch scene' })
      .evaluate((button) => {
        for (let i = 0; i < 21; i++) (button as HTMLButtonElement).click();
      });
    await page.setViewportSize({ width: 390, height: 400 });
    await expect(page.locator('.scene-experience')).toHaveAttribute(
      'data-scene',
      'horizon',
    );
    await page.getByRole('button', { name: 'Next track' }).click();
    await expect(page.getByText('Blue Hour')).toBeVisible();
    await expect.poll(() => page.evaluate(inspectConceptLayout)).toEqual([]);
  });
}

test('concept geometry oracle detects a real footer collision', async ({
  page,
}) => {
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=explorations-design-directions--orbital-console&graphics=poster',
  );
  await expect(page.locator('.design-concept')).toBeVisible();
  await page.locator('.concept-legal').evaluate((element) => {
    (element as HTMLElement).style.transform = 'translateY(-40px)';
  });
  await expect
    .poll(() => page.evaluate(inspectConceptLayout))
    .toContain('Music and registration links overlaps');
});

test('long metadata and unavailable sources keep every control inside the player', async ({
  page,
}) => {
  for (const story of ['long-metadata', 'spotify-connection']) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=music-unified-player--${story}`,
    );
    await expect(
      page.getByRole('region', { name: 'Music player' }),
    ).toBeVisible();
    for (const size of viewports) {
      await page.setViewportSize(size);
      await expect
        .poll(() =>
          page.locator('.unified-player').evaluate((player) => {
            const bounds = player.getBoundingClientRect();
            const children = Array.from(player.children).filter(
              (child) => child.getBoundingClientRect().width > 0,
            );
            const issues: string[] = [];
            for (const child of children) {
              const box = child.getBoundingClientRect();
              if (
                box.left < bounds.left - 1.5 ||
                box.right > bounds.right + 1.5
              )
                issues.push(`${child.className} overflows`);
            }
            if (document.documentElement.scrollWidth > innerWidth + 1.5)
              issues.push('Document overflow');
            return issues;
          }),
        )
        .toEqual([]);
    }
    if (story === 'spotify-connection') {
      await page.setViewportSize({ width: 320, height: 568 });
      await expect(
        page.getByRole('link', { name: /Open source/ }),
      ).toBeVisible();
    }
  }
});

test('reduced motion, keyboard controls and touch-sized transport remain available', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=explorations-design-directions--liquid-chrome&graphics=poster',
  );
  const scene = page.locator('.scene-experience');
  await expect(scene).toHaveAttribute('data-paused', 'true');
  const next = page.getByRole('button', { name: 'Next track' });
  await next.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByText('Blue Hour')).toBeVisible();
  for (const control of await page.locator('.player-transport button').all()) {
    const bounds = await control.boundingBox();
    expect(bounds!.width).toBeGreaterThanOrEqual(44);
    expect(bounds!.height).toBeGreaterThanOrEqual(44);
  }
  await expect.poll(() => page.evaluate(inspectConceptLayout)).toEqual([]);
});
