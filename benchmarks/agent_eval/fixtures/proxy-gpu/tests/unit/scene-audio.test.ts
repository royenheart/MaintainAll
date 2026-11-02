import { afterEach, describe, expect, it, vi } from 'vitest';
import content from '../../src/content/scene-music.json';
import { loadSceneTracks } from '../../src/lib/music/scene-track-schema';
import {
  musicSourceUrl,
  resolvePublicAudio,
} from '../../src/lib/music/sources';

describe('scene recording delivery', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the selected NetEase songs playable without requesting CORS analysis', async () => {
    const tracks = loadSceneTracks(content, {});
    expect(tracks.cubes.title).toBe('Clair de Lune');
    expect(tracks.horizon.title).toBe('Sanctuary');
    for (const [scene, id] of [
      ['cubes', '30953026'],
      ['horizon', '27755434'],
    ] as const) {
      await expect(
        resolvePublicAudio(tracks[scene], new AbortController().signal),
      ).resolves.toEqual({
        playback: {
          kind: 'audio',
          url: `https://music.163.com/song/media/outer/url?id=${id}.mp3`,
          analysis: 'unavailable',
        },
      });
    }
  });

  it('plays the bundled recording while preserving artist and platform links', async () => {
    const tracks = loadSceneTracks(
      {
        ...content,
        cubes: { ...content.cubes, audioFile: 'axolotl.mp3' },
        horizon: { ...content.horizon, audioFile: 'sanctuary.mp3' },
      },
      {
        'axolotl.mp3': '/_astro/axolotl.abc123.mp3',
        'sanctuary.mp3': '/_astro/sanctuary.def456.mp3',
      },
    );
    for (const scene of ['cubes', 'horizon'] as const) {
      expect(tracks[scene].artist).toBe(content[scene].artist);
      expect(tracks[scene].links).toEqual(content[scene].links);
      expect(musicSourceUrl(tracks[scene].source)).toContain('music.163.com');
      await expect(
        resolvePublicAudio(tracks[scene], new AbortController().signal),
      ).resolves.toEqual({
        playback: { kind: 'audio', url: tracks[scene].playbackUrl },
      });
    }
  });

  it('fails when a configured recording is missing instead of using an outer URL', () => {
    expect(() =>
      loadSceneTracks(
        { ...content, cubes: { ...content.cubes, audioFile: 'missing.mp3' } },
        {},
      ),
    ).toThrow('Missing scene audio file: missing.mp3');
  });

  it.each(['../private.mp3', '/audio.mp3', 'https://example.test/audio.mp3'])(
    'rejects a non-bundled audio filename: %s',
    (audioFile) => {
      expect(() =>
        loadSceneTracks(
          { ...content, cubes: { ...content.cubes, audioFile } },
          {},
        ),
      ).toThrow();
    },
  );

  it('rejects platform pages as playback overrides', async () => {
    const tracks = loadSceneTracks(content, {});
    await expect(
      resolvePublicAudio(
        { ...tracks.cubes, playbackUrl: content.cubes.sourceUrl },
        new AbortController().signal,
      ),
    ).rejects.toThrow('Playback requires an audio file');
  });

  it('supports same-origin HTTP preview assets without allowing remote HTTP media', async () => {
    vi.stubGlobal('location', new URL('http://192.0.2.10:6006/iframe.html'));
    const track = loadSceneTracks(content, {}).cubes;
    const url = 'http://192.0.2.10:6006/assets/recording.hash.mp3';
    await expect(
      resolvePublicAudio(
        { ...track, playbackUrl: url },
        new AbortController().signal,
      ),
    ).resolves.toEqual({ playback: { kind: 'audio', url } });
    await expect(
      resolvePublicAudio(
        { ...track, playbackUrl: 'http://example.test/recording.mp3' },
        new AbortController().signal,
      ),
    ).rejects.toThrow('Use an HTTPS music URL');
  });
});
