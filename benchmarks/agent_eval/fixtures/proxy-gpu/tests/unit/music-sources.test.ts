import { describe, expect, it } from 'vitest';
import {
  musicSourceUrl,
  parseMusicSource,
  resolvePublicAudio,
} from '../../src/lib/music/sources';

describe('music source normalization', () => {
  it.each([
    ['https://music.163.com/#/song?id=30953026', 'netease', '30953026'],
    ['https://music.163.com/song?id=30953026', 'netease', '30953026'],
    [
      'https://y.qq.com/n/ryqq/songDetail/003OUlho2HcRHC',
      'qq',
      '003OUlho2HcRHC',
    ],
    ['https://y.qq.com/n/yqq/song/003OUlho2HcRHC.html', 'qq', '003OUlho2HcRHC'],
    [
      'https://www.bilibili.com/video/BV1xx411c7mD/?p=2',
      'bilibili',
      'BV1xx411c7mD',
    ],
    [
      'https://open.spotify.com/intl-de/track/4cOdK2wGLETKBW3PvgPWqT?si=example',
      'spotify',
      '4cOdK2wGLETKBW3PvgPWqT',
    ],
    [
      'spotify:track:4cOdK2wGLETKBW3PvgPWqT',
      'spotify',
      '4cOdK2wGLETKBW3PvgPWqT',
    ],
  ])(
    'normalizes %s and preserves a canonical source link',
    (input, provider, id) => {
      const source = parseMusicSource(input);
      expect(source).toMatchObject({ provider, id });
      expect(parseMusicSource(musicSourceUrl(source))).toEqual(source);
    },
  );

  it('preserves direct audio queries and root-relative audio paths', () => {
    expect(
      parseMusicSource('https://audio.example.test/song.mp3?token=example'),
    ).toEqual({
      provider: 'direct',
      url: 'https://audio.example.test/song.mp3?token=example',
    });
    expect(parseMusicSource('/audio/track.mp3')).toEqual({
      provider: 'local',
      url: '/audio/track.mp3',
    });
  });

  it.each([
    'javascript:alert(1)',
    'http://example.test/audio.mp3',
    '//example.test/audio.mp3',
    '/audio/../secret',
    '/audio/%2e%2e/secret',
    '/%2fexample.test/audio.mp3',
    '/audio/%5cfile',
    'https://user:pass@example.test/track.mp3',
    'https://music.163.com/song',
    'https://y.qq.com/?songmid=../bad',
    'https://www.bilibili.com/video/BV1xx411c7mD/?p=0',
    'https://open.spotify.com/playlist/4cOdK2wGLETKBW3PvgPWqT',
  ])('rejects invalid input %s', (input) => {
    expect(() => parseMusicSource(input)).toThrow();
  });

  it('does not claim that a Spotify link is native audio', async () => {
    const result = await resolvePublicAudio(
      {
        id: 'spotify',
        title: 'Example',
        artist: 'Example',
        source: parseMusicSource('spotify:track:4cOdK2wGLETKBW3PvgPWqT'),
      },
      new AbortController().signal,
    );
    expect(result.playback.kind).toBe('external');
  });
});
