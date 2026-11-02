import { githubMarkPath } from './github-mark';

export type DockIconName =
  | 'journal'
  | 'repository'
  | 'github'
  | 'shield'
  | 'previous'
  | 'next'
  | 'play'
  | 'pause';

/** Shared, locally drawn line icons for the compact dock controls. */
export function DockIcon({ name }: { name: DockIconName }) {
  return (
    <svg
      key={name}
      className="orbit-dock-icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
      data-icon={name}
    >
      {name === 'journal' && (
        <>
          <path
            pathLength="1"
            d="M12 5C8 3 5 3 3 4v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-2-1-5-1-9 1Zm0 0v15M6 8l3 1M6 12l3 1M15 9l3-1M15 13l3-1"
          />
        </>
      )}
      {name === 'repository' && (
        <>
          <circle pathLength="1" cx="7" cy="5" r="2.5" />
          <circle pathLength="1" cx="17" cy="6" r="2.5" />
          <circle pathLength="1" cx="7" cy="19" r="2.5" />
          <path pathLength="1" d="M7 7.5v9M17 8.5v1a5 5 0 0 1-5 5H7" />
        </>
      )}
      {name === 'github' && (
        <path
          d={githubMarkPath}
          transform="scale(1.5)"
          fill="currentColor"
          stroke="none"
        />
      )}
      {name === 'shield' && (
        <>
          <path pathLength="1" d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6Z" />
          <path pathLength="1" d="m8 12 3 3 5-6" />
        </>
      )}
      {name === 'previous' && <path pathLength="1" d="M20 12H4m6-6-6 6 6 6" />}
      {name === 'next' && <path pathLength="1" d="M4 12h16m-6-6 6 6-6 6" />}
      {name === 'play' && <path pathLength="1" d="m8 5 11 7-11 7Z" />}
      {name === 'pause' && <path pathLength="1" d="M8 5v14M16 5v14" />}
    </svg>
  );
}
