import { useId, useState } from 'react';
import { motion, useTransform, type MotionValue } from 'motion/react';
import type { SceneTracks } from '../../lib/music/scene-tracks';
import type { SceneId } from '../../lib/content/schema';
import { smoothRange, type CoverStudy } from './presentation';

function CoverImage({ artwork, title }: { artwork?: string; title: string }) {
  const [result, setResult] = useState<{ url: string; ready: boolean }>();
  const ready = Boolean(artwork && result?.url === artwork && result.ready);
  return (
    <>
      {artwork && (
        <img
          src={artwork}
          alt=""
          style={{ opacity: ready ? 1 : 0 }}
          onLoad={() => setResult({ url: artwork, ready: true })}
          onError={() => setResult({ url: artwork, ready: false })}
        />
      )}
      {!ready && (
        <span
          className="orbit-artwork-placeholder"
          title={`${title} artwork ${result?.url === artwork || !artwork ? 'unavailable' : 'loading'}`}
        >
          ♫
        </span>
      )}
    </>
  );
}

/** Both covers stay mounted; the shared scene clock also drives their handoff. */
export function CoverTransition({
  tracks,
  scene,
  blend,
  effect,
  reduced,
}: {
  tracks: SceneTracks;
  scene: SceneId;
  blend: MotionValue<number>;
  effect: CoverStudy;
  reduced: boolean;
}) {
  const id = `cover-${useId().replace(/:/g, '')}`;
  const weight = useTransform(blend, (value) => smoothRange(value, 0.28, 0.86));
  const veil = useTransform(blend, (value) =>
    reduced
      ? 0
      : smoothRange(value, 0, 0.3) * (1 - smoothRange(value, 0.72, 1)),
  );
  const displacement = useTransform(veil, (value) => value * 11);
  const filter = useTransform(veil, (value) =>
    value < 0.001
      ? 'none'
      : `${effect === 'ripple' ? `url(#${id}) ` : ''}blur(${value * (effect === 'frost' ? 7 : 2)}px)`,
  );
  const mist = useTransform(
    veil,
    (value) => value * (effect === 'frost' ? 0.55 : 0.24),
  );
  const clip = useTransform(
    weight,
    (value) => `ellipse(130% ${value * 230}% at 50% 120%)`,
  );
  const rim = useTransform(weight, (value) => `${(1 - value) * 220 - 40}%`);
  return (
    <span
      className="orbit-artwork orbit-cover-transition"
      data-effect={effect}
      role="img"
      aria-label={`${tracks[scene].title} artwork`}
    >
      <svg
        className="cover-filter-definitions"
        aria-hidden="true"
        width="0"
        height="0"
      >
        <defs>
          <filter
            id={id}
            x="-25%"
            y="-25%"
            width="150%"
            height="150%"
            colorInterpolationFilters="sRGB"
          >
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.025 0.038"
              numOctaves="2"
              seed="8"
              result="water"
            />
            <motion.feDisplacementMap
              in="SourceGraphic"
              in2="water"
              scale={displacement}
              xChannelSelector="R"
              yChannelSelector="G"
            />
          </filter>
        </defs>
      </svg>
      <motion.span className="cover-material" style={{ filter }}>
        <span className="cover-layer" data-cover="cubes">
          <CoverImage
            artwork={tracks.cubes.artwork}
            title={tracks.cubes.title}
          />
        </span>
        <motion.span
          className="cover-layer"
          data-cover="horizon"
          style={
            effect === 'meniscus' && !reduced
              ? { clipPath: clip }
              : { opacity: weight }
          }
        >
          <CoverImage
            artwork={tracks.horizon.artwork}
            title={tracks.horizon.title}
          />
        </motion.span>
      </motion.span>
      <motion.span
        className="cover-mist"
        style={{ opacity: mist }}
        aria-hidden="true"
      />
      {effect === 'meniscus' && (
        <motion.span
          className="cover-meniscus"
          style={{ top: rim, opacity: veil }}
          aria-hidden="true"
        />
      )}
    </span>
  );
}
