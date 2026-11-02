import { expect, test } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

test('standalone preview retains the selected deck, tracks and responsive geometry', async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const cover of ['ripple', 'frost', 'meniscus']) {
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?scene=${scene}&graphics=poster&cover=${cover}`,
      );
      await expect(page).toHaveTitle(/Preview/);
      await expect(page.locator('iframe')).toHaveCount(0);
      await expect(page.locator('main')).toHaveAttribute(
        'data-dock-design',
        'drum',
      );
      await expect(
        page.locator('.orbit-arrival, .orbit-scene-number'),
      ).toHaveCount(0);
      await expect(page.locator('.rotary-deck')).toBeVisible();
      await expect(page.locator('.orbit-artwork')).toHaveAttribute(
        'aria-label',
        scene === 'cubes' ? 'Clair de Lune artwork' : 'Sanctuary artwork',
      );
      await expect(page.locator('.rotary-deck')).toHaveAttribute(
        'data-card-count',
        '4',
      );
      const family = 'IBM Plex Sans';
      await expect(page.locator('.orbit-sound')).toHaveCount(0);
      await expect(page.locator('.orbit-dock-registrations a')).toHaveCount(2);
      await page.evaluate(() => document.fonts.ready);
      const families = await page
        .locator(
          '.orbit-study h1, .orbit-study h2, .orbit-study p, .orbit-study a, .orbit-study button',
        )
        .evaluateAll((nodes) =>
          nodes.map((node) => getComputedStyle(node).fontFamily),
        );
      expect(
        families.every((value) => value.replaceAll('"', '').startsWith(family)),
      ).toBe(true);
      for (const size of [
        { width: 320, height: 568 },
        { width: 320, height: 320 },
        { width: 419, height: 600 },
        { width: 420, height: 600 },
        { width: 360, height: 640 },
        { width: 639, height: 450 },
        { width: 640, height: 450 },
        { width: 390, height: 400 },
        { width: 844, height: 390 },
        { width: 768, height: 1024 },
        { width: 1440, height: 900 },
      ]) {
        await page.setViewportSize(size);
        await page.locator('.rotary-deck').press('Home');
        const count = Number(
          await page.locator('.rotary-deck').getAttribute('data-card-count'),
        );
        for (let card = 0; card < count; card++) {
          await expect
            .poll(() => page.evaluate(inspectOrbitLayout))
            .toEqual([]);
          await expect
            .poll(() => page.evaluate(inspectRotaryLayout))
            .toEqual([]);
          if (card < count - 1)
            await page.locator('.rotary-deck').press('ArrowDown');
        }
      }
    }
  }
});

test('poster preview navigates to the horizon without a live canvas', async ({
  page,
}) => {
  await page.goto('/preview/?scene=cubes&graphics=poster&skipIntro=1');
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'poster');
  await expect(page.locator('main')).toHaveAttribute('data-prepared', 'true');
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
});

test('a buffering track keeps a usable pause control', async ({ page }) => {
  await page.route('**/song/media/outer/**', (route) =>
    route.fulfill({
      path: fileURLToPath(
        new URL(
          '../../src/explorations/audio-fixtures/steady-tone.mp3',
          import.meta.url,
        ),
      ),
      contentType: 'audio/mpeg',
    }),
  );
  await page.addInitScript(() => {
    const Native = window.Audio;
    window.Audio = class extends Native {
      constructor() {
        super();
        this.loop = true;
      }
    };
  });
  await page.addInitScript(() => {
    (window as unknown as { testAudio: HTMLAudioElement[] }).testAudio = [];
    const Native = window.Audio;
    window.Audio = class extends Native {
      constructor() {
        super();
        (window as unknown as { testAudio: HTMLAudioElement[] }).testAudio.push(
          this,
        );
      }
    };
  });
  await page.goto('/preview/?scene=cubes&graphics=poster&skipIntro=1');
  await page.locator('.rotary-deck').press('End');
  const play = page.getByRole('button', { name: 'Play music', exact: true });
  if (await play.isVisible()) await play.click();
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'true',
  );
  const buffering = await page.evaluate(() => {
    const audio = (
      window as unknown as { testAudio: HTMLAudioElement[] }
    ).testAudio.find((element) => !element.paused);
    if (!audio) return null;
    audio.dispatchEvent(new Event('waiting'));
    return { paused: audio.paused, time: audio.currentTime };
  });
  expect(buffering).not.toBeNull();
  const pause = page.getByRole('button', { name: 'Pause music', exact: true });
  await expect(pause).toBeEnabled();
  await pause.click();
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'false',
  );
  const stopped = await page.evaluate(() => {
    const audios = (window as unknown as { testAudio: HTMLAudioElement[] })
      .testAudio;
    return audios.map((audio) => ({
      paused: audio.paused,
      time: audio.currentTime,
    }));
  });
  expect(stopped.every((audio) => audio.paused)).toBe(true);
  await page.waitForTimeout(300);
  const later = await page.evaluate(() => {
    const audios = (window as unknown as { testAudio: HTMLAudioElement[] })
      .testAudio;
    return audios.map((audio) => audio.currentTime);
  });
  later.forEach((time, index) => {
    expect(Math.abs(time - stopped[index]!.time)).toBeLessThan(0.05);
  });
});

test('root serves the selected experience and retains the original page', async ({
  page,
}) => {
  await page.goto('/?scene=cubes&graphics=poster&skipIntro=1');
  await expect(page.locator('main')).toHaveAttribute(
    'data-interface',
    'continuous',
  );
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'poster');
  await page.goto('/original/');
  await expect(page.locator('.scene-experience')).toBeVisible();
});

test('scene switch queues while the destination is preparing', async ({
  page,
}) => {
  await page.route('**/optics/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    await route.continue();
  });
  await page.goto('/?scene=cubes&skipIntro=1');
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  await page.locator('.rotary-deck').press('End');
  const next = page.getByRole('button', { name: 'Next scene', exact: true });
  await expect(next).toBeEnabled();
  await next.click();
  await expect(page.locator('main')).toHaveAttribute(
    'data-navigation-queued',
    'true',
  );
  await expect(page.locator('main')).toHaveAttribute('data-prepared', 'true', {
    timeout: 15000,
  });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon', {
    timeout: 15000,
  });
});

test('runtime diagnostics toggle and the damaged fallback state', async ({
  page,
}) => {
  await page.goto('/?scene=cubes&skipIntro=1');
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  await page.keyboard.press('Shift+D');
  const hud = page.locator('.orbit-diagnostics');
  await expect(hud).toBeVisible();
  await expect(hud).toContainText('frame');
  await expect(hud).toContainText('renderer');
  await page.keyboard.press('Shift+D');
  await expect(hud).toHaveCount(0);

  await page
    .locator('canvas')
    .evaluate((node) =>
      node.dispatchEvent(new Event('webglcontextlost', { cancelable: true })),
    );
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await expect(page.locator('.orbit-damage')).toBeVisible();
  await expect(page.locator('.orbit-fallback')).toHaveCount(0);
  await page.keyboard.press('Shift+D');
  await expect(page.locator('.orbit-diagnostics')).toContainText('still view');
});

test('touch devices can open diagnostics without a keyboard', async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  try {
    await page.goto('/?graphics=poster&skipIntro=1');
    const trigger = page.getByRole('button', { name: 'Runtime diagnostics' });
    await expect(trigger).toBeVisible();
    await trigger.tap();
    const hud = page.locator('.orbit-diagnostics');
    await expect(hud).toBeVisible();
    await page.getByRole('button', { name: 'Close diagnostics' }).tap();
    await expect(hud).toHaveCount(0);
  } finally {
    await context.close();
  }
});
