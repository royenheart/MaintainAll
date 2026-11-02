import { expect, test } from '@playwright/test';
import sharp from 'sharp';

const url = (view: string) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-horizon&capture=1&args=skipEntrance:true;horizonDiagnostic:${view}`;

type Pixels = { data: Buffer; width: number; height: number };

// Follow an observed color region, independently of the shader's coordinate map.
// A disconnected band cannot reach the upper arc from its foreground seed.
function connectedBand(image: Pixels, seedX: number, seedY: number) {
  const { data, width, height } = image;
  const seed = seedY * width + seedX;
  const color = [data[seed * 3]!, data[seed * 3 + 1]!, data[seed * 3 + 2]!];
  const visited = new Uint8Array(width * height);
  const queue = new Int32Array(width * height);
  let start = 0;
  let end = 1;
  let minY = seedY;
  let minX = seedX;
  let maxX = seedX;
  queue[0] = seed;
  visited[seed] = 1;
  while (start < end) {
    const index = queue[start++]!;
    const x = index % width;
    const y = Math.floor(index / width);
    minY = Math.min(minY, y);
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
        const next = ny * width + nx;
        if (visited[next]) continue;
        visited[next] = 1;
        if (
          color.every(
            (channel, component) =>
              Math.abs(data[next * 3 + component]! - channel) < 22,
          )
        )
          queue[end++] = next;
      }
    }
  }
  return { color, minY, minX, maxX, area: end };
}

test('multiple material bands continue from the foreground through both junctions into the arc', async ({
  page,
}) => {
  // Expanding foreground intervals need a wider view to keep three complete
  // groups on-screen instead of clipping their outer turns at the viewport edge.
  await page.setViewportSize({ width: 1280, height: 640 });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto(url('coordinates'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const { data, info } = await sharp(await page.locator('canvas').screenshot())
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const image = { data, width: info.width, height: info.height };
  const connected: ReturnType<typeof connectedBand>[] = [];
  for (let fraction = 0.6; fraction <= 0.84; fraction += 0.01) {
    const band = connectedBand(
      image,
      Math.floor(info.width / 2),
      Math.floor(info.height * fraction),
    );
    if (
      band.minY < info.height * 0.22 &&
      // The arc scales with viewport height. Widening the capture must not
      // move the required junction positions farther away from the actual arc.
      band.minX < info.width / 2 - info.height * 0.35 &&
      band.maxX > info.width / 2 + info.height * 0.35 &&
      band.area > info.width * info.height * 0.005 &&
      connected.every((previous) =>
        previous.color.some(
          (channel, i) => Math.abs(channel - band.color[i]!) > 30,
        ),
      )
    )
      connected.push(band);
  }
  expect(
    connected.length,
    'Several distinct bands must survive the entire turn',
  ).toBeGreaterThanOrEqual(3);

  // Negative control: sever both junctions in image space. The same oracle must
  // reject the break even though the colors and both end regions still exist.
  const broken = Buffer.from(data);
  const cutY = Math.floor(info.height * 0.45);
  broken.fill(0, cutY * info.width * 3, (cutY + 4) * info.width * 3);
  const severed = connectedBand(
    { ...image, data: broken },
    Math.floor(info.width / 2),
    Math.floor(info.height * 0.68),
  );
  expect(severed.minY).toBeGreaterThan(cutY);
});

test('unbloomed emission keeps the junction lit through a viewport resize', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto(url('emission'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  for (const size of [
    { width: 960, height: 640 },
    { width: 768, height: 1024 },
    { width: 390, height: 400 },
  ]) {
    await page.setViewportSize(size);
    await expect
      .poll(async () => (await page.locator('canvas').boundingBox())?.width)
      .toBe(size.width);
    // Element screenshots include overlaid DOM. Hide the artwork control so a
    // short viewport cannot mistake its opaque album cover for a shader gap.
    const { data, info } = await sharp(
      await page.locator('canvas').screenshot({
        style: '.orbit-wheel { visibility: hidden !important; }',
      }),
    )
      .removeAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const luma = (x: number, y: number) => {
      const offset = (Math.floor(y) * info.width + Math.floor(x)) * 3;
      return (
        data[offset]! * 0.2126 +
        data[offset + 1]! * 0.7152 +
        data[offset + 2]! * 0.0722
      );
    };
    // Estimate the scale from the observed upper crest rather than shader constants.
    const profile = Array.from(
      { length: Math.floor(info.height / 2) },
      (_, y) => luma(info.width / 2, y),
    );
    const radius = info.height / 2 - profile.indexOf(Math.max(...profile));
    // Remove individual strand peaks before checking the broad emission field.
    // A raw scan crossing a valid sharp strand is not a discontinuous veil.
    const envelope = await sharp(data, {
      raw: { width: info.width, height: info.height, channels: 3 },
    })
      .blur(Math.max(1, radius * 0.018))
      .raw()
      .toBuffer();
    for (const side of [-1, 1]) {
      let previous: number | undefined;
      for (let step = 0; step <= 40; step++) {
        const y = info.height / 2 + radius * (-0.28 + step * 0.012);
        const x = info.width / 2 + side * radius * 1.08;
        const offset = (Math.floor(y) * info.width + Math.floor(x)) * 3;
        const brightness =
          envelope[offset]! * 0.2126 +
          envelope[offset + 1]! * 0.7152 +
          envelope[offset + 2]! * 0.0722;
        expect(
          brightness,
          `Dark separation at side ${side}, step ${step}`,
        ).toBeGreaterThan(28);
        if (previous !== undefined)
          expect(
            Math.abs(brightness - previous),
            'No abrupt veil boundary',
          ).toBeLessThan(65);
        previous = brightness;
      }
    }
  }
});
