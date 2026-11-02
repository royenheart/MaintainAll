import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { Playlist, Track } from '../../lib/content/schema';
import { embedUrl, trackUrl } from '../../lib/content/urls';

const playerQuery = '(min-width: 400px)';
const subscribeWidth = (notify: () => void) => {
  const media = window.matchMedia(playerQuery);
  media.addEventListener('change', notify);
  return () => media.removeEventListener('change', notify);
};
const playerFits = () => window.matchMedia(playerQuery).matches;
const serverFits = () => false;

function TrackEmbed({ track, timeoutMs }: { track: Track; timeoutMs: number }) {
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setExpired(true), timeoutMs);
    return () => window.clearTimeout(timer);
  }, [timeoutMs]);

  return (
    <div className="embed-content">
      <iframe
        title={`NetEase player: ${track.label}`}
        src={embedUrl(track)}
        width={330}
        height={86}
        referrerPolicy="no-referrer"
      />
      <p className="embed-status" role="status">
        {expired
          ? 'If the player is unavailable, open the track directly.'
          : 'Playback is provided by NetEase. Press play in the player.'}
      </p>
      <a href={trackUrl(track)} target="_blank" rel="noreferrer">
        Open track in NetEase
      </a>
    </div>
  );
}

export function MusicPanel({
  playlist,
  timeoutMs = 12000,
}: {
  playlist: Playlist;
  timeoutMs?: number;
}) {
  const [selected, setSelected] = useState(playlist.defaultTrackId);
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const wide = useSyncExternalStore(subscribeWidth, playerFits, serverFits);
  const track =
    playlist.tracks.find((item) => item.id === selected) ?? playlist.tracks[0];
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        toggle.current?.focus();
      }
    };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, [open]);

  if (!track)
    return (
      <div className="music-panel music-empty">
        <span className="music-mark" aria-hidden="true">
          ♫
        </span>
        <p>No tracks yet</p>
      </div>
    );
  return (
    <section className="music-panel" aria-label="Music">
      <span className="music-mark" aria-hidden="true">
        ♫
      </span>
      <div className="track-copy">
        <span className="eyeline">On the record</span>
        {playlist.tracks.length > 1 ? (
          <>
            <label className="sr-only" htmlFor="track-select">
              Choose a track
            </label>
            <select
              id="track-select"
              value={track.id}
              onChange={(event) => setSelected(event.target.value)}
            >
              {playlist.tracks.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </>
        ) : (
          <a
            className="track-name"
            href={trackUrl(track)}
            target="_blank"
            rel="noreferrer"
            title={track.label}
          >
            {track.label}
          </a>
        )}
      </div>
      <button
        ref={toggle}
        id="music-toggle"
        className="music-toggle"
        type="button"
        aria-expanded={open}
        aria-controls="music-player"
        onClick={() => setOpen((value) => !value)}
      >
        {open ? 'Close' : 'Listen'}
      </button>
      {open && (
        <div
          id="music-player"
          className="music-popover"
          role="region"
          aria-label="NetEase player"
        >
          {wide ? (
            <TrackEmbed key={track.id} track={track} timeoutMs={timeoutMs} />
          ) : (
            <div className="embed-narrow">
              <p>Open this track in NetEase for its full player.</p>
              <a href={trackUrl(track)} target="_blank" rel="noreferrer">
                Open track
              </a>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
