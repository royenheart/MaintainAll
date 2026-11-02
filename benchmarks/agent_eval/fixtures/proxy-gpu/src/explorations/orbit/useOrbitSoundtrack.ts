import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MotionValue } from 'motion/react';
import type { SceneId } from '../../lib/content/schema';
import type { SceneTracks } from '../../lib/music/scene-tracks';
import type { TrackResolver } from '../../lib/music/sources';
import { useOrbitAudio } from './useOrbitAudio';

function smoothstep(value: number, min: number, max: number) {
  const t = Math.min(1, Math.max(0, (value - min) / (max - min)));
  return t * t * (3 - 2 * t);
}

/** Keep both sources prepared while the same scene canvas remains mounted. */
export function useOrbitSoundtrack(
  tracks: SceneTracks,
  resolve: TrackResolver,
  scene: SceneId,
  target: SceneId | null,
  blend: MotionValue<number>,
  visible: boolean,
  onEnded: () => void,
) {
  const [wanted, setWanted] = useState(false);
  const intent = useRef(0);
  const gestureScene = useRef<SceneId | null>(null);
  const cubesId = tracks.cubes.id;
  const horizonId = tracks.horizon.id;
  useEffect(() => {
    // Any request that began before a scene or track change must not clear the
    // replacement's playback intent when its old element is paused.
    intent.current++;
    gestureScene.current = null;
  }, [scene, cubesId, horizonId]);
  const cubes = useOrbitAudio(tracks.cubes, resolve, () => {
    if (scene === 'cubes' && !target) onEnded();
  });
  const horizon = useOrbitAudio(tracks.horizon, resolve, () => {
    if (scene === 'horizon' && !target) onEnded();
  });
  const controls = useMemo(
    () => ({
      cubes: {
        play: cubes.play,
        pause: cubes.pause,
        prime: cubes.prime,
        setGain: cubes.setGain,
        element: cubes.element,
      },
      horizon: {
        play: horizon.play,
        pause: horizon.pause,
        prime: horizon.prime,
        setGain: horizon.setGain,
        element: horizon.element,
      },
    }),
    [
      cubes.play,
      cubes.pause,
      cubes.prime,
      cubes.setGain,
      cubes.element,
      horizon.play,
      horizon.pause,
      horizon.prime,
      horizon.setGain,
      horizon.element,
    ],
  );
  const play = useCallback(async () => {
    const request = ++intent.current;
    gestureScene.current = scene;
    setWanted(true);
    // Resume both contexts in the user gesture, without playing the spare deck.
    for (const deck of Object.values(controls))
      void deck.prime().catch(() => {});
    const started = await controls[scene].play();
    // A denied or failed request must not leave a false pause affordance, but
    // only the request that still owns the current intent may clear it.
    if (!started && intent.current === request) {
      gestureScene.current = null;
      setWanted(false);
    }
    return started;
  }, [controls, scene]);
  const autoplay = useCallback(async () => {
    const request = ++intent.current;
    gestureScene.current = scene;
    // A denied automatic attempt must not become a persistent playback intent.
    const started = await controls[scene].play();
    if (started && intent.current === request) setWanted(true);
    else gestureScene.current = null;
    return started;
  }, [controls, scene]);
  const pause = useCallback(() => {
    intent.current++;
    gestureScene.current = null;
    setWanted(false);
    for (const deck of Object.values(controls)) deck.pause();
  }, [controls]);
  useEffect(() => {
    if (!wanted) return;
    if (!visible) {
      // A hidden tab must not keep either crossfade deck audible. Keep the
      // playback intent so returning to the page can reconcile the current
      // scene without treating the visibility pause as a user stop.
      controls.cubes.pause();
      controls.horizon.pause();
      return;
    }
    const source = controls[scene];
    const destination = controls[scene === 'cubes' ? 'horizon' : 'cubes'];
    const ready = { cubes: cubes.ready, horizon: horizon.ready };
    if (!target) {
      destination.pause();
      destination.setGain(0);
      if (destination.element.current?.readyState)
        destination.element.current.currentTime = 0;
      source.setGain(1);
      if (gestureScene.current === scene) {
        // The gesture path already started this deck; do not supersede its
        // request and mistake the cancellation for a playback failure.
        gestureScene.current = null;
        return;
      }
      if (ready[scene]) {
        let disposed = false;
        void source.play().then((started) => {
          if (!disposed && !started) setWanted(false);
        });
        return () => {
          disposed = true;
        };
      }
      return;
    }
    let disposed = false;
    let started = false;
    const ended = source.element.current?.ended ?? false;
    destination.setGain(0);
    const update = () => {
      const progress = scene === 'cubes' ? blend.get() : 1 - blend.get();
      const weight = smoothstep(progress, ended ? 0 : 0.35, ended ? 0.12 : 1);
      // Keep the source audible if the incoming source is delayed or unavailable.
      source.setGain(started ? Math.cos((weight * Math.PI) / 2) : 1);
      destination.setGain(started ? Math.sin((weight * Math.PI) / 2) : 0);
    };
    if (ready[target])
      void destination.play().then((playing) => {
        if (disposed) return;
        started = playing;
        update();
      });
    update();
    const unsubscribe = blend.on('change', update);
    return () => {
      disposed = true;
      unsubscribe();
    };
  }, [
    wanted,
    visible,
    scene,
    target,
    blend,
    controls,
    cubes.ready,
    horizon.ready,
  ]);
  return {
    ...(scene === 'cubes' ? cubes : horizon),
    wanted,
    play,
    pause,
    autoplay,
  };
}
