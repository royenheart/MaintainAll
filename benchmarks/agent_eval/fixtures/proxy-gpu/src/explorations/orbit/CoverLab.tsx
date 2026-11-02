import { useEffect, useRef, useState } from 'react';
import {
  animate,
  useMotionValue,
  useMotionValueEvent,
  type AnimationPlaybackControls,
} from 'motion/react';
import { sceneTracks } from '../../lib/music/scene-tracks';
import { useReducedMotionPreference } from '../../lib/useReducedMotionPreference';
import { CoverTransition } from './CoverTransition';
import { presentationStudies } from './presentation';
import './orbit.css';
import './presentation.css';
import './cover-lab.css';

export function CoverLab() {
  const blend = useMotionValue(0);
  const [value, setValue] = useState(0);
  const animation = useRef<AnimationPlaybackControls | null>(null);
  const reduced = useReducedMotionPreference();
  useMotionValueEvent(blend, 'change', setValue);
  useEffect(() => {
    const stop = () => {
      if (document.hidden) animation.current?.stop();
    };
    document.addEventListener('visibilitychange', stop);
    return () => {
      animation.current?.stop();
      document.removeEventListener('visibilitychange', stop);
    };
  }, []);
  const play = (to: number) => {
    animation.current?.stop();
    animation.current = animate(blend, to, {
      duration: reduced ? 0 : Math.abs(to - blend.get()) * 6.4,
      ease: 'linear',
    });
  };
  return (
    <main className="cover-lab">
      <header>
        <p>ARTWORK HANDOFF / A · B · C</p>
        <h1>One clock. Three materials.</h1>
        <p>
          Compare the cover treatments at the same point in the scene
          transition.
        </p>
      </header>
      <div className="cover-lab-controls">
        <button onClick={() => play(1)}>To horizon</button>
        <button onClick={() => play(0)}>To Axolotl</button>
        <label>
          Transition{' '}
          <input
            type="range"
            aria-label="Transition progress"
            min="0"
            max="1"
            step="0.001"
            value={value}
            onChange={(event) => {
              animation.current?.stop();
              blend.set(Number(event.target.value));
            }}
          />
        </label>
      </div>
      <div className="cover-lab-grid">
        {Object.entries(presentationStudies).map(([id, study]) => (
          <section
            key={id}
            className="orbit-study cover-lab-sample"
            data-interface="continuous"
            data-font={study.font}
          >
            <p>
              {id.toUpperCase()} / {study.font}
            </p>
            <h2>
              {study.cover === 'ripple'
                ? 'Ripple refraction'
                : study.cover === 'frost'
                  ? 'Frosted diffusion'
                  : 'Liquid meniscus'}
            </h2>
            <div className="cover-lab-disc orbit-disc">
              <CoverTransition
                tracks={sceneTracks}
                scene={value > 0.5 ? 'horizon' : 'cubes'}
                blend={blend}
                effect={study.cover}
                reduced={reduced}
              />
            </div>
            <p>
              {study.cover === 'ripple'
                ? 'A soft displacement field bends both images beneath a translucent film.'
                : study.cover === 'frost'
                  ? 'A milky layer diffuses detail before the next cover resolves.'
                  : 'A curved liquid boundary sweeps upward to reveal the next image.'}
            </p>
            <a
              href={`/preview/?variant=${id}`}
              target="_blank"
              rel="noreferrer"
            >
              Open the full scene ↗
            </a>
          </section>
        ))}
      </div>
    </main>
  );
}
