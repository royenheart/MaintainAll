import { useMemo, type CSSProperties } from 'react';
import type { SceneId } from '../../lib/content/schema';

type Severity = 'low' | 'high' | 'fault';

interface Shard {
  left: number;
  top: number;
  width: number;
  height: number;
  rotate: number;
  dx: number;
  dy: number;
  delay: number;
  duration: number;
  tone: string;
}

function shardsFor(scene: SceneId): Shard[] {
  // Deterministic shard identities keep the damage field stable across React
  // renders while still looking irregular.
  let state = scene === 'cubes' ? 0x51f15e : 0x9e3779b9;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
  const tones =
    scene === 'cubes'
      ? ['#72f7ff', '#168cff', '#ff4b6e', '#c7fbff']
      : ['#ffc45c', '#ff7a1a', '#fff1bd', '#8a3b12'];
  return Array.from({ length: scene === 'cubes' ? 24 : 20 }, () => ({
    left: random() * 96,
    top: random() * 92,
    width: 18 + random() * (scene === 'cubes' ? 90 : 70),
    height: 2 + random() * (scene === 'cubes' ? 56 : 18),
    rotate: -42 + random() * 84,
    dx: -18 + random() * 36,
    dy: -14 + random() * 28,
    delay: -random() * 8,
    duration: 2.4 + random() * 5.6,
    tone: tones[Math.floor(random() * tones.length)]!,
  }));
}

export function DamageField({
  scene,
  active,
  severity,
}: {
  scene: SceneId;
  active: boolean;
  severity: Severity;
}) {
  const shards = useMemo(() => shardsFor(scene), [scene]);
  if (!active) return null;
  return (
    <div
      className={`orbit-damage orbit-damage-${scene}`}
      data-severity={severity}
      aria-hidden="true"
    >
      <div className="orbit-damage-scanlines" />
      <div className="orbit-damage-wash" />
      <span className="orbit-damage-pane orbit-damage-pane-a" />
      <span className="orbit-damage-pane orbit-damage-pane-b" />
      <span className="orbit-damage-pane orbit-damage-pane-c" />
      {scene === 'horizon' && <div className="orbit-damage-core" />}
      {shards.map((shard, index) => (
        <span
          key={index}
          className="orbit-damage-shard"
          style={
            {
              left: `${shard.left}%`,
              top: `${shard.top}%`,
              width: `${shard.width}px`,
              height: `${shard.height}px`,
              background: `linear-gradient(90deg, transparent, ${shard.tone}, transparent)`,
              '--damage-rotate': `${shard.rotate}deg`,
              '--damage-dx': `${shard.dx}px`,
              '--damage-dy': `${shard.dy}px`,
              '--damage-delay': `${shard.delay}s`,
              '--damage-duration': `${shard.duration}s`,
            } as CSSProperties
          }
        />
      ))}
      <svg
        className="orbit-damage-cracks"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path d="M -2 18 L 18 22 L 24 30 L 37 26 L 49 41 L 66 37 L 78 51 L 102 46" />
        <path d="M 8 102 L 12 80 L 27 74 L 31 57 L 44 50 L 52 31 L 67 20 L 72 0" />
        <path d="M 102 72 L 84 68 L 80 56 L 66 61 L 58 49 L 43 55 L 31 44 L 0 51" />
      </svg>
      {shards.slice(0, 6).map((shard, index) => (
        <span
          key={`block-${index}`}
          className="orbit-damage-block"
          style={
            {
              left: `${shard.left}%`,
              top: `${shard.top}%`,
              width: `${Math.max(14, shard.width * 0.7)}px`,
              height: `${Math.max(12, shard.height * 0.8)}px`,
              '--damage-delay': `${shard.delay}s`,
            } as CSSProperties
          }
        />
      ))}
      <span className="orbit-damage-tear orbit-damage-tear-a" />
      <span className="orbit-damage-tear orbit-damage-tear-b" />
      <span className="orbit-damage-tear orbit-damage-tear-c" />
    </div>
  );
}
