import type { CardFinish } from './card-finishes';

export function CardFinishLayer({
  finish,
  contour,
  id,
}: {
  finish: CardFinish;
  contour: string;
  id: string;
}) {
  if (finish === 'original') return null;
  return (
    <g className="card-finish-layer">
      <defs>
        <linearGradient id={`${id}-coat`} x2="0" y2="1">
          <stop stopColor="var(--finish-coat)" stopOpacity="0.7" />
          <stop offset="0.48" stopColor="var(--finish-coat)" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.32" />
        </linearGradient>
        <linearGradient id={`${id}-reflection`}>
          <stop stopColor="var(--orbit-accent)" stopOpacity="0" />
          <stop
            offset="0.5"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.18"
          />
          <stop offset="1" stopColor="var(--orbit-accent)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${id}-ambient`}>
          <stop stopColor="var(--orbit-accent)" stopOpacity="0" />
          <stop
            offset="0.5"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.14"
          />
          <stop offset="1" stopColor="var(--orbit-accent)" stopOpacity="0" />
        </linearGradient>
        <linearGradient
          id={`${id}-enamel`}
          gradientUnits="userSpaceOnUse"
          x1="-60"
          x2="380"
          y1="0"
          y2="100"
        >
          <stop stopColor="var(--orbit-accent)" stopOpacity="0" />
          <stop
            offset="0.2"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.012"
          />
          <stop
            offset="0.48"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.04"
          />
          <stop
            offset="0.76"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.066"
          />
          <stop
            offset="1"
            stopColor="var(--orbit-accent)"
            stopOpacity="0.075"
          />
        </linearGradient>
        <pattern
          id={`${id}-mesh`}
          width="9"
          height="9"
          patternUnits="userSpaceOnUse"
        >
          <circle cx="2" cy="2" r="0.7" fill="var(--orbit-accent)" />
        </pattern>
      </defs>
      <path d={contour} fill={`url(#${id}-coat)`} />
      {finish === 'inset' && (
        <>
          <path d={contour} fill={`url(#${id}-mesh)`} opacity="0.09" />
          <path
            d={contour}
            transform="translate(7 10) scale(.973 .8)"
            className="finish-recess"
          />
          <path d="M42 13H568" className="finish-inner-highlight" />
        </>
      )}
      {finish === 'nameplate' && (
        <>
          <g className="finish-enamel-field finish-material-motion">
            <path d="M-120 -30H740V130H-120Z" fill={`url(#${id}-enamel)`} />
          </g>
          <g className="finish-inlay-field finish-material-motion">
            <path
              d="M435 0h7l-29 100h-7Zm16 0h3l-29 100h-3Z"
              className="finish-inlay"
            />
          </g>
          <path
            d="M-400 -20H700V120H-400Z"
            fill={`url(#${id}-ambient)`}
            className="finish-light-field finish-material-motion"
          />
          <path
            d={contour}
            transform="translate(5 6) scale(.983 .88)"
            className="finish-lining"
          />
          <path d="M45 8H572M45 92H572" className="finish-inner-highlight" />
        </>
      )}
      {finish === 'seam' && (
        <>
          <path d="M-40 105Q130 -10 345 35T650 -40" className="finish-smoke" />
          <path d="M-40 140Q175 30 345 60T650 -10" className="finish-smoke" />
          <path
            d={contour}
            transform="translate(5 5) scale(.983 .9)"
            className="finish-lining"
          />
        </>
      )}
      <path
        d="M-150 0H-35L-75 100H-190Z"
        fill={`url(#${id}-reflection)`}
        className="finish-reflection"
      />
    </g>
  );
}
