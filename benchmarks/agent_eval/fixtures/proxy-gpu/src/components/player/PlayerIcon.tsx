export function PlayerIcon({
  name,
}: {
  name:
    'play' | 'pause' | 'previous' | 'next' | 'volume' | 'muted' | 'external';
}) {
  const paths = {
    play: 'm8 5 11 7-11 7Z',
    pause: 'M8 5v14M16 5v14',
    previous: 'M5 5v14m13-14L7 12l11 7Z',
    next: 'M19 5v14M6 5l11 7-11 7Z',
    volume: 'M4 9h4l5-4v14l-5-4H4ZM17 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
    muted: 'M4 9h4l5-4v14l-5-4H4Zm13 0 5 6m0-6-5 6',
    external: 'M14 4h6v6m0-6L10 14M10 5H5v14h14v-5',
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill={name === 'play' ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
