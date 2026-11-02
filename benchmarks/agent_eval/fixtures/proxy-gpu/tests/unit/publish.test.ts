import {
  mkdtemp,
  mkdir,
  writeFile,
  readlink,
  readFile,
  rm,
} from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { afterEach, expect, it } from 'vitest';
import { publish } from '../../deploy/publish.mjs';

const directories: string[] = [];
afterEach(async () => {
  await Promise.all(
    directories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});
async function fixture() {
  const directory = await mkdtemp(join(tmpdir(), 'proxy-publish-'));
  directories.push(directory);
  const artifact = join(directory, 'dist');
  const root = join(directory, 'deployment');
  await mkdir(join(artifact, '_astro'), { recursive: true });
  await writeFile(
    join(artifact, 'index.html'),
    '<script src="/_astro/first.123.js"></script>',
  );
  await writeFile(join(artifact, '404.html'), 'Not found');
  await writeFile(join(artifact, '_astro/first.123.js'), 'first');
  await writeFile(join(artifact, '_astro/recording.123.mp3'), 'audio fixture');
  await mkdir(join(artifact, 'preview'), { recursive: true });
  await writeFile(
    join(artifact, 'preview/index.html'),
    '<script src="/_astro/first.123.js"></script>Preview',
  );
  await mkdir(join(artifact, 'optics'), { recursive: true });
  await writeFile(join(artifact, 'optics/deflection.dat'), 'table');
  await mkdir(join(artifact, 'licenses/fonts'), { recursive: true });
  await writeFile(join(artifact, 'licenses/fonts/plex.txt'), 'license');
  return { artifact, root };
}
it('publishes atomically and preserves old lazy assets and a rollback target', async () => {
  const paths = await fixture();
  await publish({ ...paths, release: 'abcdef1' });
  await rm(join(paths.artifact, '_astro/first.123.js'));
  await rm(join(paths.artifact, '_astro/recording.123.mp3'));
  await rm(join(paths.artifact, 'preview/index.html'));
  await writeFile(join(paths.artifact, '_astro/second.456.js'), 'second');
  await writeFile(
    join(paths.artifact, 'index.html'),
    '<script src="/_astro/second.456.js"></script>',
  );
  await publish({ ...paths, release: 'abcdef2' });
  expect(await readlink(join(paths.root, 'current'))).toBe('releases/abcdef2');
  expect(await readlink(join(paths.root, 'previous'))).toBe('releases/abcdef1');
  expect(
    await readFile(join(paths.root, 'shared/_astro/first.123.js'), 'utf8'),
  ).toBe('first');
  expect(
    await readFile(join(paths.root, 'shared/_astro/recording.123.mp3'), 'utf8'),
  ).toBe('audio fixture');
});
it('rejects broken artifacts without changing the active release', async () => {
  const paths = await fixture();
  await publish({ ...paths, release: 'abcdef1' });
  await writeFile(
    join(paths.artifact, 'index.html'),
    '<script src="/_astro/missing.js"></script>',
  );
  await expect(publish({ ...paths, release: 'abcdef2' })).rejects.toThrow(
    'Missing referenced asset',
  );
  expect(await readlink(join(paths.root, 'current'))).toBe('releases/abcdef1');
});
it('refuses to overwrite immutable assets and existing releases', async () => {
  const paths = await fixture();
  await publish({ ...paths, release: 'abcdef1' });
  await expect(publish({ ...paths, release: 'abcdef1' })).rejects.toThrow(
    'already exists',
  );
  await writeFile(join(paths.artifact, '_astro/first.123.js'), 'changed');
  await expect(publish({ ...paths, release: 'abcdef2' })).rejects.toThrow(
    'Immutable asset collision',
  );
});

it('rejects sensitive-looking files even inside allowed directories', async () => {
  const paths = await fixture();
  await writeFile(join(paths.artifact, '_astro/.env.production'), 'secret');
  await expect(publish({ ...paths, release: 'abcdef3' })).rejects.toThrow(
    'unexpected files',
  );
  await rm(join(paths.artifact, '_astro/.env.production'));
  await writeFile(join(paths.artifact, 'optics/debug.log'), 'log');
  await expect(publish({ ...paths, release: 'abcdef4' })).rejects.toThrow(
    'unexpected files',
  );
  await rm(join(paths.artifact, 'optics/debug.log'));
  await writeFile(join(paths.artifact, 'licenses/private.pem'), 'key');
  await expect(publish({ ...paths, release: 'abcdef5' })).rejects.toThrow(
    'unexpected files',
  );
});
