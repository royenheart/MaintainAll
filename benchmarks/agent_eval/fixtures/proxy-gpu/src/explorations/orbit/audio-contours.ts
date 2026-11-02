export interface AudioContourLevels {
  energy: number;
  low: number;
  mid: number;
  high: number;
}

export const quietLevels = (): AudioContourLevels => ({
  energy: 0,
  low: 0,
  mid: 0,
  high: 0,
});

// A gentle decorative cycle for playback without readable samples. This is
// deliberately separate from measured energy, including a genuinely silent track.
export const ambientLevels = (time: number): AudioContourLevels => ({
  energy: 0.34 + 0.07 * Math.sin(time * 0.7),
  low: 0.3 + 0.1 * Math.sin(time * 0.53),
  mid: 0.25 + 0.1 * Math.cos(time * 0.71),
  high: 0.12 + 0.06 * Math.sin(time * 0.91),
});

// Frequency magnitudes shape the lobes; measured waveform energy gates motion,
// so a silent playing source cannot produce a simulated beat.
export function measureContourAudio(
  frequency: Uint8Array,
  waveform: Uint8Array,
): AudioContourLevels {
  let squares = 0;
  for (const sample of waveform) squares += ((sample - 128) / 128) ** 2;
  const rms = Math.sqrt(squares / waveform.length);
  const band = (start: number, end: number) => {
    let sum = 0;
    for (let i = start; i < end; i++) sum += frequency[i] ?? 0;
    return sum / ((end - start) * 255);
  };
  return {
    energy: Math.min(1, Math.max(0, rms - 0.004) * 5),
    low: band(1, 5),
    mid: band(5, 24),
    high: band(24, 96),
  };
}

// Periodic angular harmonics make broad, crossing contours rather than bars.
// Closed cubic interpolation preserves a smooth seam at the first sample.
export function audioContourPath(
  layer: number,
  time: number,
  levels: AudioContourLevels,
) {
  const count = 64;
  const points = Array.from({ length: count }, (_, index) => {
    const angle = (index / count) * Math.PI * 2;
    const phase = layer * 1.1 + time * (0.24 + layer * 0.035);
    const shape =
      (2.3 + levels.low * 2.8) * Math.sin(angle * 2 + phase) +
      (1.3 + levels.mid * 1.8) * Math.cos(angle * 3 - phase * 0.8) +
      (0.5 + levels.high * 1.1) * Math.sin(angle * 5 + phase * 0.6);
    // Smooth saturation keeps a readable swell inside the cover clearance
    // without flattening strong peaks against a hard radius clamp.
    const radius =
      90 + layer * 0.45 + 7 * Math.tanh((levels.energy * shape) / 3);
    return [100 + Math.cos(angle) * radius, 100 + Math.sin(angle) * radius];
  });
  const at = (index: number) => points[(index + count) % count]!;
  const format = (value: number) => value.toFixed(2);
  let path = `M${at(0).map(format).join(' ')}`;
  for (let index = 0; index < count; index++) {
    const [p0, p1, p2, p3] = [
      at(index - 1),
      at(index),
      at(index + 1),
      at(index + 2),
    ];
    const c1 = p1!.map((value, axis) => value + (p2![axis]! - p0![axis]!) / 6);
    const c2 = p2!.map((value, axis) => value - (p3![axis]! - p1![axis]!) / 6);
    path += `C${[...c1, ...c2, ...p2!].map(format).join(' ')}`;
  }
  return `${path}Z`;
}
