import { useId } from 'react';
import type { SceneId } from '../../lib/content/schema';
import type { CardArtStudy } from './card-finishes';

const facets = [
  'M70 132 111 68 140 104 105 163Z',
  'M111 68 171 35 140 104Z',
  'M171 35 213 78 181 141 140 104Z',
  'M140 104 181 141 153 183 105 163Z',
  'M213 78 241 112 209 170 181 141Z',
];
const cubeCells = [
  [126, 80, 26],
  [170, 102, 34],
  [114, 131, 23],
  [212, 134, 30],
  [161, 154, 29],
] as const;

/** Original vector studies: scene-specific printing, not additional UI controls. */
export function SceneCardArt({
  scene,
  study,
}: {
  scene: SceneId;
  study: CardArtStudy;
}) {
  const id = useId();
  const horizon = scene === 'horizon';
  return (
    <svg
      className="scene-card-art"
      data-art={study}
      data-scene={scene}
      viewBox="0 0 240 180"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={`${id}-foil`} x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="var(--art-secondary)" stopOpacity=".18" />
          <stop offset=".36" stopColor="var(--orbit-accent)" stopOpacity=".5" />
          <stop offset=".51" stopColor="var(--art-pearl)" stopOpacity=".65" />
          <stop
            offset=".63"
            stopColor="var(--orbit-accent)"
            stopOpacity=".12"
          />
          <stop offset="1" stopColor="var(--art-secondary)" stopOpacity=".45" />
        </linearGradient>
        <linearGradient id={`${id}-relief`} x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="var(--orbit-accent)" stopOpacity=".25" />
          <stop offset=".5" stopColor="var(--finish-base)" />
          <stop offset="1" stopColor="var(--art-secondary)" stopOpacity=".4" />
        </linearGradient>
      </defs>
      {study === 'engraving' && (
        <g stroke="currentColor" strokeWidth=".7" opacity=".54">
          {horizon ? (
            <>
              {Array.from({ length: 16 }, (_, i) => (
                <path
                  key={i}
                  d={`M${20 - i * 2} ${154 + i * 4}C${101 - i * 2} ${152 + i * 2} ${83 - i * 1.4} ${49 - i * 1.8} 163 ${48 - i * 1.5}C${207 + i * 2} ${46 - i} ${212 + i * 2.8} ${130 + i * 2} 248 ${130 + i * 3}`}
                />
              ))}
              <path d="M59 147C95 132 89 59 145 48" strokeWidth="1.4" />
            </>
          ) : (
            <>
              {Array.from({ length: 12 }, (_, i) => (
                <path
                  key={i}
                  d={`M${50 + i * 3} 180V${121 - i * 3}L${121 + i * 3} ${79 - i * 3}L${192 + i * 3} ${119 - i * 3}V180M${121 + i * 3} ${79 - i * 3}V180`}
                />
              ))}
              <path d="m98 89 62-36 61 34-61 36Zm62-36v70" />
              <path d="m82 153 79-46 76 44" strokeWidth="1.4" />
            </>
          )}
        </g>
      )}
      {study === 'foil' && (
        <g stroke="var(--orbit-accent)" strokeWidth=".6" strokeOpacity=".35">
          {horizon ? (
            <>
              <path
                d="M30 161C125 142 78 33 163 31 233 29 196 131 253 147L232 167C168 149 219 51 163 52 104 53 144 162 43 178Z"
                fill={`url(#${id}-foil)`}
              />
              <path
                d="M22 166C126 116 212 185 242 106L249 142C209 200 106 141 22 174Z"
                fill={`url(#${id}-foil)`}
              />
              <path
                d="M42 166C139 139 100 43 166 42"
                stroke="var(--art-pearl)"
              />
              <path d="M164 52C202 58 180 133 226 159" />
            </>
          ) : (
            <>
              {facets.map((d, i) => (
                <path
                  key={d}
                  d={d}
                  fill={`url(#${id}-foil)`}
                  opacity={i % 2 ? 0.6 : 1}
                />
              ))}
              <path
                d="m111 68 60-33-31 69 41 37 32-63"
                stroke="var(--art-pearl)"
              />
              <path
                d="m53 146 24-38 18 18-22 36Z"
                fill={`url(#${id}-foil)`}
                opacity=".4"
              />
            </>
          )}
        </g>
      )}
      {study === 'relief' && (
        <g
          fill={`url(#${id}-relief)`}
          stroke="var(--orbit-accent)"
          strokeOpacity=".32"
          strokeWidth=".8"
        >
          {horizon ? (
            <>
              {[0, 1, 2, 3].map((i) => (
                <g key={i} transform={`translate(${i * 5} ${i * 8})`}>
                  <path d="M62 120C104 100 106 38 165 42 212 45 199 110 237 132L224 140C181 117 201 59 164 58 119 57 121 118 69 136Z" />
                  <path
                    d="M62 120C104 100 106 38 165 42"
                    stroke="var(--art-pearl)"
                    strokeOpacity=".4"
                  />
                </g>
              ))}
              <path d="M52 146Q138 192 234 153" fill="none" />
            </>
          ) : (
            cubeCells.map(([x, y, size]) => (
              <g key={x}>
                <path
                  d={`M${x} ${y - size}l${size} ${size * 0.56}v${size}l${-size} ${size * 0.58}-${size} ${-size * 0.58}v${-size}Z`}
                />
                <path
                  d={`M${x - size} ${y - size * 0.44}l${size} ${size * 0.56} ${size} ${-size * 0.56}M${x} ${y + size * 0.12}v${size * 1.02}`}
                  fill="none"
                />
                <path
                  d={`M${x - size} ${y - size * 0.44}l${size} ${-size * 0.56} ${size} ${size * 0.56}`}
                  stroke="var(--art-pearl)"
                  strokeOpacity=".4"
                />
              </g>
            ))
          )}
        </g>
      )}
    </svg>
  );
}
