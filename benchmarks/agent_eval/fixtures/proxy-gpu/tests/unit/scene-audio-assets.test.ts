import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, expect, it } from 'vitest';
import { checkSceneAudio } from '../../scripts/scene-audio.mjs';
import content from '../../src/content/scene-music.json';

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(
    directories
      .splice(0)
      .map((path) => rm(path, { recursive: true, force: true })),
  );
});

async function fixture(files: { cubes?: string; horizon?: string }) {
  const root = await mkdtemp(join(tmpdir(), 'proxy-audio-check-'));
  directories.push(root);
  await mkdir(join(root, 'src/content'), { recursive: true });
  await mkdir(join(root, 'src/assets/audio'), { recursive: true });
  await writeFile(
    join(root, 'src/content/scene-music.json'),
    JSON.stringify({
      cubes: { ...content.cubes, audioFile: files.cubes },
      horizon: { ...content.horizon, audioFile: files.horizon },
    }),
  );
  return root;
}

it('reports missing recordings without claiming playback readiness', async () => {
  const root = await fixture({});
  await expect(checkSceneAudio(root)).resolves.toEqual({
    installed: 0,
    missing: ['cubes', 'horizon'],
  });
  await expect(checkSceneAudio(root, true)).rejects.toThrow(
    'Recordings not installed: cubes, horizon',
  );
});

it('rejects absent and empty configured assets', async () => {
  const root = await fixture({ cubes: 'missing.mp3' });
  await expect(checkSceneAudio(root)).rejects.toThrow('Missing or empty');
  await writeFile(join(root, 'src/assets/audio/missing.mp3'), '');
  await expect(checkSceneAudio(root)).rejects.toThrow('Missing or empty');
});

it('rejects paths outside the bundled asset directory', async () => {
  const root = await fixture({ cubes: '../secret.mp3' });
  await expect(checkSceneAudio(root)).rejects.toThrow('Invalid audio filename');
  expect(
    await readFile(join(root, 'src/content/scene-music.json'), 'utf8'),
  ).toContain('../secret.mp3');
});
