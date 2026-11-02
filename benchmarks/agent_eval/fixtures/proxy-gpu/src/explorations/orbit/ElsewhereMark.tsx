import { useId } from 'react';
import { githubMarkPath } from './github-mark';
import type { ElsewhereMark as MarkStudy } from './card-finishes';

function GitHubSeal({
  x,
  y,
  size,
  fill,
}: {
  x: number;
  y: number;
  size: number;
  fill: string;
}) {
  return (
    <svg
      x={x}
      y={y}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill={fill}
      stroke="none"
    >
      <path d={githubMarkPath} />
    </svg>
  );
}

/** Semantic silhouettes stay prominent; secondary marks suggest printed stock. */
export function ElsewhereMark({
  kind,
  study,
}: {
  kind: 'blog' | 'github';
  study: MarkStudy;
}) {
  const id = useId();
  const foil = `url(#${id}-foil)`;
  return (
    <svg
      className="elsewhere-miniature elsewhere-mark"
      data-mark={study}
      data-kind={kind}
      viewBox="0 0 80 32"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={`${id}-foil`} x1="0" x2="1" y1="0" y2="1">
          <stop stopColor="var(--orbit-accent)" stopOpacity=".85" />
          <stop offset=".42" stopColor="var(--orbit-accent)" stopOpacity=".6" />
          <stop offset=".54" stopColor="var(--mark-pearl)" />
          <stop offset="1" stopColor="var(--orbit-accent)" stopOpacity=".75" />
        </linearGradient>
      </defs>
      {study === 'emblem' && (
        <>
          <path d="M12 25h7m42 0h7M15 28h10m30 0h10" opacity=".2" />
          {kind === 'github' ? (
            <GitHubSeal x={27} y={3} size={26} fill={foil} />
          ) : (
            <g strokeLinecap="round" strokeLinejoin="round">
              <path
                d="M40 7c-5-4-11-4-16-3v21c6-1 11 0 16 3 5-3 10-4 16-3V4c-5-1-11-1-16 3Z"
                fill={foil}
                stroke="none"
              />
              <path
                d="M40 7v21m-12-18 8 2m-8 3 8 2m8-5 8-2m-8 7 8-2"
                stroke="var(--finish-base)"
                strokeWidth="1.4"
              />
            </g>
          )}
        </>
      )}
      {study === 'intaglio' && (
        <>
          <path
            d="M13 7h7M12 11h6M11 15h6M10 19h7m43-12h7m-6 4h7m-6 4h7m-7 4h8"
            opacity=".25"
          />
          {kind === 'github' ? (
            <>
              <path d="M23 5q17-7 34 0v22q-17 6-34 0Z" opacity=".4" />
              <GitHubSeal x={29} y={5} size={22} fill="currentColor" />
            </>
          ) : (
            <g strokeLinecap="round" strokeLinejoin="round">
              <path
                d="M27 4h27v23H27q-5 0-5-4V8q0-4 5-4Zm0 0v19m-5 0h32M45 4v10l-4-3-4 3V4m-6 13h9"
                strokeWidth="1.3"
              />
              <path d="M24 27h33V7" opacity=".3" />
            </g>
          )}
        </>
      )}
      {study === 'editorial' && (
        <>
          <path
            d="M9 5h59l4 4v18H9Z"
            fill={foil}
            fillOpacity=".12"
            strokeOpacity=".38"
          />
          {kind === 'github' ? (
            <>
              <GitHubSeal x={15} y={7} size={20} fill={foil} />
              <path
                d="m48 10-5 5 5 5m12-10 5 5-5 5m-5-10-3 11"
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path d="M42 24h22" opacity=".25" />
            </>
          ) : (
            <g strokeLinecap="round" strokeLinejoin="round">
              <path
                d="M15 10h19v13H15Z"
                fill={foil}
                fillOpacity=".38"
                strokeOpacity=".6"
              />
              <path
                d="M24 11v11m-6-8 3 1m6 0 4-1m-13 4 3 1m6 0 4-1M40 10h22m-22 5h25m-25 5h17m-42 7h42"
                strokeWidth="1.15"
              />
            </g>
          )}
        </>
      )}
    </svg>
  );
}
