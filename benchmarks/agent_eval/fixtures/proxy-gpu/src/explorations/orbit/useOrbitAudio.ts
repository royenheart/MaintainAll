import { useCallback, useEffect, useRef, useState } from 'react';
import type { MusicTrack, TrackResolver } from '../../lib/music/sources';

export function useOrbitAudio(
  track: MusicTrack,
  resolve: TrackResolver,
  onEnded: () => void,
) {
  const element = useRef<HTMLAudioElement | null>(null);
  const analyser = useRef<AnalyserNode | null>(null);
  const context = useRef<AudioContext | null>(null);
  const source = useRef<MediaElementAudioSourceNode | null>(null);
  const gain = useRef<GainNode | null>(null);
  const canAnalyse = useRef(true);
  const level = useRef(1);
  const requested = useRef(false);
  const request = useRef(0);
  const inflight = useRef<{
    audio: HTMLAudioElement;
    promise: Promise<boolean>;
  } | null>(null);
  const ended = useRef(onEnded);
  const [status, setStatus] = useState<{
    id: string;
    ready: boolean;
    playing: boolean;
    blocked: boolean;
    error: string | null;
    time: number;
    duration: number;
  }>({
    id: '',
    ready: false,
    playing: false,
    blocked: false,
    error: null,
    time: 0,
    duration: 0,
  });
  useEffect(() => {
    ended.current = onEnded;
  }, [onEnded]);
  useEffect(() => {
    const controller = new AbortController();
    const audio = new Audio();
    audio.preload = 'auto';
    canAnalyse.current = true;
    element.current = audio;
    const update = (values: Partial<typeof status>) => {
      if (!controller.signal.aborted)
        setStatus((old) => ({ ...old, id: track.id, ...values }));
    };
    const ready = () => {
      clearTimeout(timeout);
      update({
        ready: true,
        error: null,
        duration: Number.isFinite(audio.duration) ? audio.duration : 0,
      });
    };
    const playing = () =>
      update({ playing: true, blocked: false, error: null });
    const paused = () => update({ playing: false });
    const tick = () => update({ time: audio.currentTime });
    const finish = () => {
      paused();
      ended.current();
    };
    const failed = () =>
      update({
        playing: false,
        blocked: false,
        ready: false,
        error: 'Sound is unavailable. You can continue quietly.',
      });
    const listeners = {
      canplay: ready,
      playing,
      pause: paused,
      waiting: paused,
      timeupdate: tick,
      ended: finish,
      error: failed,
    };
    for (const [name, handler] of Object.entries(listeners))
      audio.addEventListener(name, handler);
    update({
      ready: false,
      playing: false,
      blocked: false,
      error: null,
      time: 0,
      duration: 0,
    });
    const timeout = window.setTimeout(() => {
      // A mobile browser may defer preloading until play() is requested.
      // Only unresolved sources time out here; readiness is not permission.
      if (!audio.getAttribute('src')) failed();
    }, 8000);
    resolve(track, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.playback.kind !== 'audio') {
          clearTimeout(timeout);
          update({
            ready: false,
            playing: false,
            error: result.playback.message,
          });
          return;
        }
        canAnalyse.current = result.playback.analysis !== 'unavailable';
        if (canAnalyse.current) audio.crossOrigin = 'anonymous';
        else {
          analyser.current = null;
          audio.volume = level.current;
        }
        audio.src = result.playback.url;
        update({ ready: true });
        audio.load();
      })
      .catch(failed);
    return () => {
      requested.current = false;
      inflight.current = null;
      controller.abort();
      clearTimeout(timeout);
      for (const [name, handler] of Object.entries(listeners))
        audio.removeEventListener(name, handler);
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
      source.current?.disconnect();
      source.current = null;
      void context.current?.close().catch(() => {});
      context.current = null;
      analyser.current = null;
      gain.current = null;
      if (element.current === audio) element.current = null;
    };
  }, [track, resolve]);
  const pause = useCallback(() => {
    inflight.current = null;
    request.current++;
    requested.current = false;
    element.current?.pause();
    setStatus((old) => ({ ...old, blocked: false }));
  }, []);
  const setGain = useCallback((value: number) => {
    level.current = Math.max(0, Math.min(1, value));
    if (!canAnalyse.current && element.current)
      element.current.volume = level.current;
    if (gain.current && context.current)
      gain.current.gain.setTargetAtTime(
        level.current,
        context.current.currentTime,
        0.025,
      );
  }, []);
  const prime = useCallback(async () => {
    if (!canAnalyse.current) return;
    if (!context.current) {
      try {
        context.current = new AudioContext();
        analyser.current = context.current.createAnalyser();
        analyser.current.fftSize = 256;
        analyser.current.smoothingTimeConstant = 0.8;
        gain.current = context.current.createGain();
        gain.current.gain.value = level.current;
        analyser.current.connect(gain.current);
        gain.current.connect(context.current.destination);
      } catch {
        // Analysis support is optional; ordinary media playback remains usable.
        void context.current?.close().catch(() => {});
        context.current = null;
        analyser.current = null;
        gain.current = null;
        canAnalyse.current = false;
        if (element.current) element.current.volume = level.current;
        return;
      }
    }
    await context.current.resume();
  }, []);
  const play = useCallback(async () => {
    const audio = element.current;
    // A rewound deck can temporarily have only its current frame decoded.
    // play() must wake that pipeline and wait for data, rather than abandoning
    // the handoff until a canplay event that may itself depend on playback.
    if (!audio || !audio.getAttribute('src') || audio.error) return false;
    const existing = inflight.current;
    // The gesture path and the reconciliation effect can both request the same
    // deck within one render. Reuse the pending attempt instead of incrementing
    // the request generation and cancelling the gesture's own playback.
    if (existing?.audio === audio) return existing.promise;
    requested.current = true;
    const promise = (async () => {
      if (!audio.paused && !audio.ended) {
        // A browser can suspend the Web Audio graph while the media element
        // keeps reporting playback. Re-enter the gesture path so a resumed
        // deck is not silently left suspended.
        const intent = ++request.current;
        try {
          await prime();
        } catch {
          return false;
        }
        return request.current === intent && element.current === audio;
      }
      const intent = ++request.current;
      try {
        const primed = prime();
        if (canAnalyse.current && !source.current) {
          source.current = context.current!.createMediaElementSource(audio);
          source.current.connect(analyser.current!);
          // Re-prime decoded media after attaching its Web Audio output. WebKit's
          // preloaded MP3 pipeline can otherwise report playing without advancing.
          audio.load();
        }
        await Promise.all([primed, audio.play()]);
        if (request.current !== intent || element.current !== audio) {
          if (!requested.current || element.current !== audio) audio.pause();
          return false;
        }
        return true;
      } catch (error) {
        if (request.current === intent && element.current === audio)
          setStatus((old) => ({
            ...old,
            playing: false,
            blocked:
              error instanceof DOMException && error.name === 'NotAllowedError',
            error:
              error instanceof DOMException && error.name === 'NotAllowedError'
                ? 'Tap the scene or press play to enable sound.'
                : 'Sound could not start. Press play to try again.',
          }));
        return false;
      }
    })();
    inflight.current = { audio, promise };
    try {
      return await promise;
    } finally {
      if (inflight.current?.promise === promise) inflight.current = null;
    }
  }, [prime]);
  const current =
    status.id === track.id
      ? status
      : {
          ready: false,
          playing: false,
          blocked: false,
          error: null,
          time: 0,
          duration: 0,
        };
  return { ...current, element, analyser, play, pause, prime, setGain };
}
