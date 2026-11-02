import { expect, test } from '@playwright/test';

test('bundled MP3 starts from zero with real output and resumes without a seek', async ({
  page,
}) => {
  await page.addInitScript(() => {
    type Probe = { media: HTMLAudioElement[]; analysers: AnalyserNode[] };
    const scope = window as unknown as { audioProbe: Probe };
    scope.audioProbe = { media: [], analysers: [] };
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor(src?: string) {
        super(src);
        scope.audioProbe.media.push(this);
      }
    };
    const NativeContext = window.AudioContext;
    window.AudioContext = class extends NativeContext {
      createAnalyser() {
        const analyser = super.createAnalyser();
        scope.audioProbe.analysers.push(analyser);
        return analyser;
      }
    };
  });
  for (const scene of ['cubes', 'horizon']) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--bundled-sound-check&args=initialScene:${scene}`,
    );
    await expect(page.locator('.orbit-sound')).toBeEnabled();
    await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
    const sample = () =>
      page.evaluate(() => {
        const probe = (
          window as unknown as {
            audioProbe: {
              media: HTMLAudioElement[];
              analysers: AnalyserNode[];
            };
          }
        ).audioProbe;
        return {
          time: Math.max(...probe.media.map((audio) => audio.currentTime)),
          rms: Math.max(
            0,
            ...probe.analysers.map((analyser) => {
              const samples = new Float32Array(analyser.fftSize);
              analyser.getFloatTimeDomainData(samples);
              return Math.sqrt(
                samples.reduce((sum, value) => sum + value * value, 0) /
                  samples.length,
              );
            }),
          ),
        };
      });
    expect((await sample()).time).toBe(0);
    await page.getByRole('button', { name: 'Play music', exact: true }).click();
    await expect.poll(async () => (await sample()).time).toBeGreaterThan(0.2);
    await expect.poll(async () => (await sample()).rms).toBeGreaterThan(0.001);
    await expect
      .poll(() =>
        page
          .locator('.orbit-spectrum')
          .getAttribute('data-energy')
          .then(Number),
      )
      .toBeGreaterThan(0);
    await page
      .getByRole('button', { name: 'Pause music', exact: true })
      .click();
    await expect
      .poll(() =>
        page
          .locator('.orbit-spectrum')
          .getAttribute('data-energy')
          .then(Number),
      )
      .toBe(0);
    const paused = (await sample()).time;
    await page.getByRole('button', { name: 'Play music', exact: true }).click();
    await expect
      .poll(async () => (await sample()).time)
      .toBeGreaterThan(paused + 0.2);
    await expect.poll(async () => (await sample()).rms).toBeGreaterThan(0.001);
  }
});
