import { expect, test, type Page } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';

const story = (name = 'external-sound-check', scene = 'cubes') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--${name}&args=initialScene:${scene}`;

type Probe = {
  media: HTMLAudioElement[];
  sources: number;
  failSamples: boolean;
};
async function probe(page: Page, loop = true) {
  await page.addInitScript((loop) => {
    const scope = window as unknown as { audioProbe: Probe };
    scope.audioProbe = { media: [], sources: 0, failSamples: false };
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        this.loop = loop;
        scope.audioProbe.media.push(this);
      }
    };
    const source = AudioContext.prototype.createMediaElementSource;
    AudioContext.prototype.createMediaElementSource = function (element) {
      scope.audioProbe.sources++;
      return source.call(this, element);
    };
    const read = AnalyserNode.prototype.getByteFrequencyData;
    AnalyserNode.prototype.getByteFrequencyData = function (array) {
      if (scope.audioProbe.failSamples) throw new Error('Samples unavailable');
      read.call(this, array);
    };
  }, loop);
}
const mediaState = (page: Page) =>
  page.evaluate(() => {
    const probe = (window as unknown as { audioProbe: Probe }).audioProbe;
    return {
      sources: probe.sources,
      media: probe.media.map((audio) => ({
        time: audio.currentTime,
        playing: !audio.paused && !audio.ended,
        volume: audio.volume,
        cors: audio.crossOrigin,
      })),
    };
  });
const shape = (page: Page) =>
  page
    .locator('.orbit-spectrum')
    .evaluate((ring) =>
      [...ring.querySelectorAll('path, line')].map(
        (node) => node.getAttribute('d') ?? node.getAttribute('y2'),
      ),
    );
async function play(page: Page) {
  await expect(page.locator('.orbit-sound')).toBeEnabled();
  await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
  await page.getByRole('button', { name: 'Play music', exact: true }).click();
}
async function nextScene(page: Page) {
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
}

test('external playback uses ambient bars and contours with pause and reduced-motion rest', async ({
  page,
}) => {
  await probe(page);
  for (const scene of ['cubes', 'horizon']) {
    await page.goto(story(undefined, scene));
    const ring = page.locator('.orbit-spectrum');
    const rest = await shape(page);
    await expect(ring).toHaveAttribute('data-response', 'rest');
    await play(page);
    await expect
      .poll(async () =>
        Math.max(...(await mediaState(page)).media.map((a) => a.time)),
      )
      .toBeGreaterThan(0.3);
    await expect(ring).toHaveAttribute('data-response', 'ambient');
    await expect(ring).toHaveAttribute('data-energy', '0');
    const moving = await shape(page);
    expect(moving).not.toEqual(rest);
    await expect.poll(() => shape(page)).not.toEqual(moving);
    const state = await mediaState(page);
    expect(state.sources).toBe(0);
    expect(state.media.every((a) => a.cors === null)).toBe(true);
    for (const size of [
      { width: 390, height: 400 },
      { width: 768, height: 1024 },
      { width: 1440, height: 900 },
    ]) {
      await page.setViewportSize(size);
      await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
    }
    await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
    await page
      .getByRole('button', { name: 'Pause music', exact: true })
      .click();
    await expect.poll(() => shape(page)).toEqual(rest);
    await expect(ring).toHaveAttribute('data-response', 'rest');
    const paused = Math.max(
      ...(await mediaState(page)).media.map((a) => a.time),
    );
    await play(page);
    await expect
      .poll(async () =>
        Math.max(...(await mediaState(page)).media.map((a) => a.time)),
      )
      .toBeGreaterThan(paused + 0.2);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect.poll(() => shape(page)).toEqual(rest);
    await expect(ring).toHaveAttribute('data-response', 'rest');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(ring).toHaveAttribute('data-response', 'ambient');
  }
});

test('analysis failure falls back without confusing readable silence with missing samples', async ({
  page,
}) => {
  await probe(page);
  await page.goto(story('bundled-sound-check', 'horizon'));
  await play(page);
  const ring = page.locator('.orbit-spectrum');
  await expect(ring).toHaveAttribute('data-response', 'audio');
  await page.evaluate(() => {
    (window as unknown as { audioProbe: Probe }).audioProbe.failSamples = true;
  });
  await expect(ring).toHaveAttribute('data-response', 'ambient');
  await expect(ring).toHaveAttribute('data-energy', '0');
  const moving = await shape(page);
  await expect.poll(() => shape(page)).not.toEqual(moving);
  await page.evaluate(() => {
    (window as unknown as { audioProbe: Probe }).audioProbe.failSamples = false;
  });
  await expect(ring).toHaveAttribute('data-response', 'audio');
  await expect
    .poll(async () => Number(await ring.getAttribute('data-energy')))
    .toBeGreaterThan(0);
});

test('missing Web Audio support preserves native playback and ambient motion', async ({
  page,
}) => {
  await probe(page);
  await page.addInitScript(() =>
    Object.defineProperty(window, 'AudioContext', { value: undefined }),
  );
  await page.goto(story('bundled-sound-check', 'horizon'));
  await play(page);
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'ambient',
  );
  await expect
    .poll(async () =>
      Math.max(...(await mediaState(page)).media.map((a) => a.time)),
    )
    .toBeGreaterThan(0.3);
  expect((await mediaState(page)).sources).toBe(0);
});

test('external decks hand off with native volume and natural completion still advances the scene', async ({
  page,
}) => {
  await probe(page, false);
  await page.goto(story());
  await play(page);
  await nextScene(page);
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
  await expect
    .poll(async () =>
      (await mediaState(page)).media.map((a) => [a.playing, a.volume]),
    )
    .toEqual([
      [false, 0],
      [true, 1],
    ]);
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'ambient',
  );
  await page.evaluate(() => {
    const audio = (window as unknown as { audioProbe: Probe }).audioProbe
      .media[1]!;
    audio.currentTime = audio.duration - 0.25;
  });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes');
  await expect
    .poll(async () =>
      (await mediaState(page)).media.map((a) => [a.playing, a.volume]),
    )
    .toEqual([
      [true, 1],
      [false, 0],
    ]);
  await expect
    .poll(async () => (await mediaState(page)).media[0]!.time)
    .toBeGreaterThan(0.2);
  await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await nextScene(page);
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon');
  expect((await mediaState(page)).media.every((a) => !a.playing)).toBe(true);
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'rest',
  );
});
