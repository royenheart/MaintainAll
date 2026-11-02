import { embedUrl } from '../../src/lib/content/urls';
import { describe, expect, it } from 'vitest';
import {
  playlistSchema,
  siteSchema,
  scenesSchema,
} from '../../src/lib/content/schema';
import { playlist, site, scenes } from '../../src/lib/content/load';
import { seededRandom } from '../../src/scenes/random';

describe('build-time content contracts', () => {
  it('preserves the current track, links, and two scenes', () => {
    expect(playlist.tracks[0]?.songId).toBe('30953026');
    expect(site.links.map((link) => link.href)).toContain(
      'https://royenheart.github.io',
    );
    expect(scenes.defaultScene).toBe('cubes');
    expect(scenes.horizon.background).toBe('#1a0b00');
  });
  it('rejects duplicate IDs and dangling defaults', () => {
    expect(
      playlistSchema.safeParse({
        ...playlist,
        tracks: [...playlist.tracks, ...playlist.tracks],
      }).success,
    ).toBe(false);
    expect(
      playlistSchema.safeParse({ ...playlist, defaultTrackId: 'missing' })
        .success,
    ).toBe(false);
    expect(
      playlistSchema.safeParse({ defaultTrackId: null, tracks: [] }).success,
    ).toBe(true);
  });
  it('rejects executable URLs, arbitrary embeds, invalid colors and budgets', () => {
    expect(
      siteSchema.safeParse({
        ...site,
        links: [{ label: 'Bad link', href: 'javascript:alert(1)' }],
      }).success,
    ).toBe(false);
    expect(
      playlistSchema.safeParse({ ...playlist, iframe: '<script />' }).success,
    ).toBe(false);
    expect(
      scenesSchema.safeParse({ ...scenes, cubeCount: 100000 }).success,
    ).toBe(false);
    expect(
      scenesSchema.safeParse({
        ...scenes,
        cubes: { ...scenes.cubes, background: 'url(x)' },
      }).success,
    ).toBe(false);
  });
  it('builds an HTTPS player with autoplay disabled', () => {
    const url = new URL(embedUrl(playlist.tracks[0]!));
    expect(url.origin).toBe('https://music.163.com');
    expect(url.searchParams.get('auto')).toBe('0');
  });
  it('has reproducible art without shared random state', () => {
    const first = seededRandom(82371);
    const second = seededRandom(82371);
    expect(Array.from({ length: 20 }, first.random)).toEqual(
      Array.from({ length: 20 }, second.random),
    );
    expect(() => first.pick([])).toThrow();
  });
});
