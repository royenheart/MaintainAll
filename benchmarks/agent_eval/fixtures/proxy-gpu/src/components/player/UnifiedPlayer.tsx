import { useEffect, useRef, useState, type CSSProperties } from 'react';
import {
  musicSourceUrl,
  providerNames,
  resolvePublicAudio,
  type MusicTrack,
  type ResolvedTrack,
  type TrackResolver,
} from '../../lib/music/sources';
import { PlayerIcon } from './PlayerIcon';
import './player.css';

const stamp = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, '0')}`;

export function UnifiedPlayer({
  tracks,
  resolveTrack = resolvePublicAudio,
}: {
  tracks: MusicTrack[];
  resolveTrack?: TrackResolver;
}) {
  const [index, setIndex] = useState(0);
  const [revision, setRevision] = useState(0);
  const [wanted, setWanted] = useState(false);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [resolved, setResolved] = useState<{
    id: string;
    value: ResolvedTrack;
  } | null>(null);
  const [error, setError] = useState<{ id: string; text: string } | null>(null);
  const [position, setPosition] = useState({
    id: '',
    time: 0,
    duration: 0,
    seekable: false,
  });
  const [muted, setMuted] = useState(false);
  const audio = useRef<HTMLAudioElement>(null);
  const pendingSeek = useRef<{
    element: HTMLAudioElement;
    time: number;
  } | null>(null);
  const track = tracks[index % Math.max(tracks.length, 1)];
  const id = track?.id;
  const value = resolved && resolved.id === id ? resolved.value : null;
  const message = error && error.id === id ? error.text : null;
  const url = value?.playback.kind === 'audio' ? value.playback.url : undefined;
  const playing = playingId === id;
  const time = position.id === id ? position.time : 0;
  const duration =
    (position.id === id && position.duration) || track?.duration || 0;
  const title = value?.title ?? track?.title;
  const artist = value?.artist ?? track?.artist;
  const artwork = value?.artwork ?? track?.artwork;

  useEffect(() => {
    if (!track) return;
    const controller = new AbortController();
    resolveTrack(track, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted)
          setResolved({ id: track.id, value: result });
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError({
            id: track.id,
            text: 'Track unavailable. Try another track or open the source.',
          });
      });
    return () => controller.abort();
  }, [track, resolveTrack, revision]);

  useEffect(() => {
    const element = audio.current;
    if (!element || !id || !url) return;
    let active = true;
    if (wanted)
      element.play().catch(() => {
        if (active) {
          setWanted(false);
          setError({
            id,
            text: 'Playback could not start. Press play to try again.',
          });
        }
      });
    else element.pause();
    return () => {
      active = false;
      element.pause();
    };
  }, [id, url, wanted]);

  const advance = (step: number) => {
    pendingSeek.current = null;
    setResolved(null);
    setError(null);
    setPlayingId(null);
    setPosition({ id: '', time: 0, duration: 0, seekable: false });
    setRevision((current) => current + 1);
    setIndex((current) => (current + step + tracks.length) % tracks.length);
  };
  if (!track)
    return (
      <section
        className="unified-player player-empty"
        aria-label="Music player"
      >
        <span>No tracks yet</span>
      </section>
    );
  const external = value?.playback.kind === 'external';
  return (
    <section
      className="unified-player"
      aria-label="Music player"
      data-playing={playing}
      data-track={track.id}
    >
      <audio
        key={`${id}-${revision}`}
        ref={audio}
        src={url}
        preload="none"
        muted={muted}
        onPlaying={() => setPlayingId(track.id)}
        onPause={() =>
          setPlayingId((current) => (current === track.id ? null : current))
        }
        onTimeUpdate={(event) =>
          setPosition({
            id: track.id,
            time: event.currentTarget.currentTime,
            seekable: event.currentTarget.seekable.length > 0,
            duration: Number.isFinite(event.currentTarget.duration)
              ? event.currentTarget.duration
              : 0,
          })
        }
        onDurationChange={(event) =>
          setPosition({
            id: track.id,
            time: event.currentTarget.currentTime,
            seekable: event.currentTarget.seekable.length > 0,
            duration: Number.isFinite(event.currentTarget.duration)
              ? event.currentTarget.duration
              : 0,
          })
        }
        onEnded={() => {
          setPlayingId(null);
          if (tracks.length > 1) advance(1);
          else setWanted(false);
        }}
        onSeeked={(event) => {
          const pending = pendingSeek.current;
          if (
            pending?.element === event.currentTarget &&
            event.currentTarget === audio.current
          ) {
            pendingSeek.current = null;
            event.currentTarget.currentTime = pending.time;
          }
        }}
        onError={() => {
          setWanted(false);
          setPlayingId(null);
          setError({
            id: track.id,
            text: 'Audio unavailable. Try another track or open the source.',
          });
        }}
      />
      <div className="player-artwork">
        {artwork ? (
          <img src={artwork} alt={`${title} cover`} width={72} height={72} />
        ) : (
          <span aria-hidden="true">♫</span>
        )}
      </div>
      <div className="player-copy">
        <span className="player-origin">
          <i aria-hidden="true" />
          {providerNames[track.source.provider]}
        </span>
        <strong className="player-title" title={title}>
          {title}
        </strong>
        <span className="player-artist" title={artist}>
          {artist}
        </span>
      </div>
      <div
        className="player-transport"
        role="group"
        aria-label="Playback controls"
      >
        <button
          type="button"
          aria-label="Previous track"
          onClick={() => advance(-1)}
          disabled={tracks.length < 2}
        >
          <PlayerIcon name="previous" />
        </button>
        <button
          className="player-play"
          type="button"
          aria-label={wanted && !external ? 'Pause music' : 'Play music'}
          disabled={!url}
          onClick={() => {
            setError(null);
            setWanted((current) => !current);
          }}
        >
          <PlayerIcon name={wanted && !external ? 'pause' : 'play'} />
        </button>
        <button
          type="button"
          aria-label="Next track"
          onClick={() => advance(1)}
          disabled={tracks.length < 2}
        >
          <PlayerIcon name="next" />
        </button>
      </div>
      <div className="player-timeline">
        <input
          type="range"
          aria-label="Track position"
          min={0}
          max={duration || 1}
          step={0.1}
          value={Math.min(time, duration || 1)}
          disabled={
            !url ||
            position.id !== id ||
            !position.duration ||
            !position.seekable
          }
          style={
            {
              '--played': `${duration ? (time / duration) * 100 : 0}%`,
            } as CSSProperties
          }
          onInput={(event) => {
            // Leave a small decoded tail; Firefox rejects near-EOF WAV seek packets.
            const next = Math.min(
              Number(event.currentTarget.value),
              Math.max(0, duration - 0.25),
            );
            if (audio.current && Number.isFinite(audio.current.duration)) {
              if (audio.current.seeking)
                pendingSeek.current = { element: audio.current, time: next };
              else audio.current.currentTime = next;
              setPosition({
                id: track.id,
                time: next,
                duration,
                seekable: true,
              });
            }
          }}
        />
        <div className="player-time" aria-hidden="true">
          <span>{stamp(time)}</span>
          <span>{stamp(duration)}</span>
        </div>
      </div>
      <div className="player-utilities">
        <button
          type="button"
          aria-label={muted ? 'Unmute music' : 'Mute music'}
          onClick={() => setMuted((current) => !current)}
        >
          <PlayerIcon name={muted ? 'muted' : 'volume'} />
        </button>
        {track.source.provider !== 'local' && (
          <a
            href={musicSourceUrl(track.source)}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open in ${providerNames[track.source.provider]}`}
          >
            <PlayerIcon name="external" />
          </a>
        )}
      </div>
      {(message || external) && (
        <p className="player-message" role="status">
          {message ??
            (value?.playback.kind === 'external' ? value.playback.message : '')}
          {track.source.provider !== 'local' && (
            <>
              {' '}
              <a
                href={musicSourceUrl(track.source)}
                target="_blank"
                rel="noreferrer"
              >
                Open source ↗
              </a>
            </>
          )}
        </p>
      )}
    </section>
  );
}
