import { expect, test, type Page } from '@playwright/test';
import sharp from 'sharp';
import { inspectOrbitLayout } from '../support/orbit-layout';

const story = (name: string) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--${name}`;
const difference = (a: Buffer, b: Buffer) =>
  a.reduce((sum, value, i) => sum + Math.abs(value - b[i]!), 0) / a.length;

test('all five junctions keep the same canvas, advancing clock and continuous pixels', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 800, height: 500 });
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=explorations-continuous-journey--selected-b',
  );
  await expect(page.locator('main')).toHaveAttribute('data-ready', 'true', {
    timeout: 15000,
  });
  await page
    .locator('canvas')
    .evaluate((canvas) => canvas.setAttribute('data-original', 'true'));
  const frame = async (time: number) => {
    await page.getByRole('slider').fill(String(Number(time.toFixed(2))));
    await expect
      .poll(() => page.evaluate(() => window.__orbitScene?.time))
      .toBeCloseTo(12 + time, 4);
    return sharp(
      await page.locator('canvas').screenshot({
        scale: 'css',
        style: '.formation-controls { visibility: hidden; }',
      }),
    )
      .removeAlpha()
      .raw()
      .toBuffer();
  };
  const seams = [];
  for (const boundary of [4.8, 8, 14.4, 18, 24.4]) {
    const before = await frame(boundary - 0.01);
    const after = await frame(boundary + 0.01);
    const change = difference(before, after);
    seams.push({ boundary, change });
    expect(change, `Boundary at ${boundary}s`).toBeLessThan(2);
  }
  const settled = await frame(14.4);
  const moving = await frame(17.4);
  expect(difference(settled, moving)).toBeGreaterThan(1);
  await expect(page.locator('canvas[data-original=true]')).toHaveCount(1);
  await test.info().attach('boundary-measurements', {
    body: JSON.stringify(seams),
    contentType: 'application/json',
  });
});

interface AudioProbe {
  decks: HTMLAudioElement[];
  gains: GainNode[];
  pauses: { index: number; scene?: string; time: number }[];
}
async function probe(page: Page) {
  await page.addInitScript(() => {
    const scope = window as unknown as { audioProbe: AudioProbe };
    scope.audioProbe = { decks: [], gains: [], pauses: [] };
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        // Manual navigation checks must not race the short fixture's natural end.
        // The natural-completion behavior is exercised separately in orbit.spec.ts.
        this.loop = true;
        scope.audioProbe.decks.push(this);
      }
      override pause() {
        scope.audioProbe.pauses.push({
          index: scope.audioProbe.decks.indexOf(this),
          scene: document.querySelector('main')?.dataset.scene,
          time: this.currentTime,
        });
        super.pause();
      }
    };
    const createGain = AudioContext.prototype.createGain;
    AudioContext.prototype.createGain = function () {
      const gain = createGain.call(this);
      scope.audioProbe.gains.push(gain);
      return gain;
    };
  });
}
async function audioState(page: Page) {
  return page.evaluate(() => {
    const scope = window as unknown as { audioProbe: AudioProbe };
    return {
      decks: scope.audioProbe.decks.map((audio) => ({
        ready: audio.readyState,
        playing: !audio.paused && !audio.ended,
        time: audio.currentTime,
      })),
      gains: scope.audioProbe.gains.map((gain) => gain.gain.value),
      pauses: scope.audioProbe.pauses,
    };
  });
}
async function nextScene(page: Page) {
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
}

test('arrival, manual B and F7 keep the canvas alive and crossfade prepared audio', async ({
  page,
}) => {
  test.setTimeout(65000);
  await page.setViewportSize({ width: 800, height: 500 });
  await probe(page);
  await page.goto(story('selected-sound-check'));
  const main = page.locator('main');
  await expect(main).toHaveAttribute('data-renderer', 'webgl', {
    timeout: 15000,
  });
  await expect(main).toHaveAttribute('data-intro-done', 'true');
  await expect
    .poll(
      async () =>
        (await audioState(page)).decks.filter((deck) => deck.ready >= 3).length,
    )
    .toBe(2);
  expect((await audioState(page)).decks.every((deck) => !deck.playing)).toBe(
    true,
  );
  const arrived = await page.evaluate(() => window.__orbitScene!.time);
  await page
    .locator('canvas')
    .evaluate((canvas) => canvas.setAttribute('data-original', 'true'));
  await page.getByRole('button', { name: 'Enter with sound' }).click();
  await expect(page.locator('.orbit-arrival')).toHaveCount(0);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.time))
    .toBeGreaterThan(arrived);
  await nextScene(page);
  await expect(main).toHaveAttribute('data-transitioning', 'true');
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBeGreaterThan(0.6);
  const middle = await audioState(page);
  expect(middle.decks.filter((deck) => deck.playing)).toHaveLength(2);
  expect(middle.gains.every((gain) => gain > 0.05)).toBe(true);
  await expect(main).toHaveAttribute('data-scene', 'horizon');
  await expect(main).toHaveAttribute('data-transitioning', 'false');
  expect((await audioState(page)).decks).toHaveLength(2);
  const end = await audioState(page);
  expect(end.decks[0]!.playing).toBe(false);
  expect(end.decks[1]!.playing).toBe(true);
  expect(end.decks[1]!.time).toBeGreaterThan(4);
  await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await nextScene(page);
  await page.setViewportSize({ width: 390, height: 400 });
  await expect(main).toHaveAttribute('data-scene', 'cubes');
  expect((await audioState(page)).decks.every((deck) => !deck.playing)).toBe(
    true,
  );
  await expect(page.locator('canvas[data-original=true]')).toHaveCount(1);
  await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
});

test('a missing destination track never freezes the visual handoff', async ({
  page,
}) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 800, height: 500 });
  await probe(page);
  await page.goto(`${story('unavailable-next-track')}&args=skipEntrance:true`);
  const main = page.locator('main');
  await expect(main).toHaveAttribute('data-renderer', 'webgl', {
    timeout: 15000,
  });
  await expect(main).toHaveAttribute('data-audio-ready', 'true');
  await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
  await page.getByRole('button', { name: 'Play music', exact: true }).click();
  await nextScene(page);
  await expect(main).toHaveAttribute('data-scene', 'horizon');
  await expect(main).toHaveAttribute('data-transitioning', 'false');
  const pauses = (await audioState(page)).pauses.filter(
    (event) => event.index === 0 && event.time > 0,
  );
  expect(pauses.length).toBeGreaterThan(0);
  expect(pauses.every((event) => event.scene === 'horizon')).toBe(true);
  await expect(main).toHaveAttribute('data-audio-ready', 'false');
  const time = await page.evaluate(() => window.__orbitScene!.time);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.time))
    .toBeGreaterThan(time);
});
