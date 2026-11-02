import type { MusicTrack, TrackResolver } from '../lib/music/sources';
import { resolvePublicAudio } from '../lib/music/sources';
import cover from './clair-de-lune.jpg?url';
import cubes from '../assets/cubes.webp?url';
import horizon from '../assets/horizon.webp?url';

export const previewTracks: MusicTrack[] = [
  {
    id: 'clair-de-lune',
    title: 'Clair de Lune',
    artist: 'Claude Debussy',
    artwork: cover,
    duration: 306.573,
    source: { provider: 'netease', id: '30953026' },
  },
  {
    id: 'blue-hour',
    title: 'Blue Hour',
    artist: 'Original preview tone',
    artwork: cubes,
    duration: 12,
    source: { provider: 'local', url: '/audio/blue-hour.wav' },
  },
  {
    id: 'golden-orbit',
    title: 'Golden Orbit',
    artist: 'Original preview tone',
    artwork: horizon,
    duration: 12,
    source: { provider: 'local', url: '/audio/golden-orbit.wav' },
  },
];

// Original synthetic audio for interaction previews; never a substitute for a platform recording.
const previewAudio = new Map<number, string>();
function tone(root: number) {
  const cached = previewAudio.get(root);
  if (cached) return cached;
  const rate = 8000;
  const duration = 12;
  const count = rate * duration;
  const bytes = new Uint8Array(44 + count * 2);
  const view = new DataView(bytes.buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++)
      bytes[offset + i] = value.charCodeAt(i);
  };
  text(0, 'RIFF');
  view.setUint32(4, bytes.length - 8, true);
  text(8, 'WAVE');
  text(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, 'data');
  view.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) {
    const t = i / rate;
    const envelope = Math.min(1, t, duration - t) * 0.07;
    const sample =
      [1, 1.25, 1.5].reduce(
        (sum, ratio) => sum + Math.sin(t * root * ratio * Math.PI * 2),
        0,
      ) * envelope;
    view.setInt16(44 + i * 2, sample * 32767, true);
  }
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const url = `data:audio/wav;base64,${btoa(binary)}`;
  previewAudio.set(root, url);
  return url;
}

export const resolvePreviewTrack: TrackResolver = async (track, signal) => {
  if (track.id === 'blue-hour' || track.id === 'golden-orbit')
    return {
      playback: {
        kind: 'audio',
        url: tone(track.id === 'blue-hour' ? 220 : 164.81),
      },
    };
  return resolvePublicAudio(track, signal);
};

// A real, silent PCM stream distinguishes playback state from audible energy.
export const resolveSilentPreviewTrack: TrackResolver = async () => ({
  playback: { kind: 'audio', url: tone(0) },
});
