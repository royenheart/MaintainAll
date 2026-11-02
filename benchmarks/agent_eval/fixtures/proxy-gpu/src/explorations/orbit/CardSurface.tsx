import { useId } from 'react';
import type { RotaryDesign } from './rotary-designs';
import type { CardFinish } from './card-finishes';
import { CardFinishLayer } from './CardFinishLayer';

const contours: Record<RotaryDesign, string> = {
  tangent:
    'M18 2H582Q598 2 598 18V82Q598 98 582 98H90Q76 98 68 87L6 24Q-5 2 18 2Z',
  drum: 'M48 2H574Q598 2 598 26V74Q598 98 574 98H48C-13 98-13 2 48 2Z',
  orbit:
    'M30 2H578Q598 2 598 22V78Q598 98 578 98H114C76 98 72 75 44 53C26 39-12 2 30 2Z',
};

export function CardSurface({
  design,
  finish = 'original',
}: {
  design: RotaryDesign;
  finish?: CardFinish;
}) {
  const id = useId().replaceAll(':', '');
  const path = contours[design];
  return (
    <svg
      className="rotary-surface"
      viewBox="0 0 600 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <clipPath id={id}>
          <path d={path} />
        </clipPath>
      </defs>
      <path d={path} className="rotary-surface-base" />
      <g clipPath={`url(#${id})`}>
        <g className="rotary-cube-texture">
          {design === 'tangent' &&
            Array.from({ length: 16 }, (_, i) => {
              const x = i * 46 - 35;
              const y = ((i * 31) % 80) - 15;
              return (
                <path
                  key={i}
                  d={`M${x} ${y}l36 -9 19 23 -35 17Z m36 -9 -2 40 m2 -40 19 23`}
                />
              );
            })}
          {design === 'drum' &&
            Array.from({ length: 26 }, (_, i) => (
              <path
                key={i}
                d={`M0 ${i * 4}Q${160 + i * 3} ${i * 4 - 10} 600 ${i * 4 + 7}`}
              />
            ))}
          {design === 'orbit' &&
            Array.from({ length: 13 }, (_, i) => (
              <path
                key={i}
                d={`M-20 ${i * 10}C130 ${i * 7 - 55} 230 ${i * 13 + 70} 640 ${i * 8 - 25}`}
              />
            ))}
        </g>
        <g className="rotary-horizon-texture">
          {design === 'tangent' &&
            Array.from({ length: 17 }, (_, i) => (
              <ellipse
                key={i}
                cx="490"
                cy="115"
                rx={45 + i * 18}
                ry={15 + i * 7}
                transform="rotate(-13 430 100)"
              />
            ))}
          {design === 'drum' &&
            Array.from({ length: 60 }, (_, i) => (
              <path
                key={i}
                d={`M${(i * 83) % 590} ${(i * 37) % 98} l${16 + (i % 33)} ${i % 2 ? -1 : 1}`}
              />
            ))}
          {design === 'orbit' &&
            Array.from({ length: 15 }, (_, i) => (
              <path
                key={i}
                d={`M-20 ${i * 9}C140 ${i * 4 - 30} 270 ${i * 12 + 12} 350 ${i * 7 + 8}S490 ${i * 3 - 15} 620 ${i * 9}`}
              />
            ))}
        </g>
        <g className="rotary-grain">
          {Array.from({ length: 72 }, (_, i) => (
            <circle
              key={i}
              cx={(i * 137 + 19) % 600}
              cy={(i * 53 + 11) % 100}
              r={i % 4 === 0 ? 0.85 : 0.45}
            />
          ))}
        </g>
        <path className="rotary-surface-sheen" d="M10 7H590M92 94H582" />
        <CardFinishLayer finish={finish} contour={path} id={id} />
      </g>
      <path
        d={path}
        className="rotary-surface-edge"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
