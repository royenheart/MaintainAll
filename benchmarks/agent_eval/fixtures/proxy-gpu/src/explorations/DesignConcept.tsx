import { useRef } from 'react';
import { useSpring, motion } from 'motion/react';
import { SceneExperience } from '../components/scene/SceneExperience';
import { UnifiedPlayer } from '../components/player/UnifiedPlayer';
import { useReducedMotionPreference } from '../lib/useReducedMotionPreference';
import { site, scenes } from '../lib/content/load';
import { previewTracks, resolvePreviewTrack } from './music-fixtures';
import avatar from '../assets/avatar.webp?url';
import cubes from '../assets/cubes.webp?url';
import horizon from '../assets/horizon.webp?url';
import './concepts.css';

export type Direction = 'orbital' | 'liquid' | 'gallery' | 'pop';
export const directions = {
  orbital: {
    title: 'Orbital Console',
    subtitle: 'A personal listening station.',
    tag: 'Space ranger',
    mark: 'R/H',
  },
  liquid: {
    title: 'Liquid Chrome',
    subtitle: 'A little space to drift.',
    tag: 'In my orbit',
    mark: 'rh',
  },
  gallery: {
    title: 'Quiet Gallery',
    subtitle: 'Sounds, scenes and small discoveries.',
    tag: 'A personal collection',
    mark: 'Rh.',
  },
  pop: {
    title: 'Pop Circuit',
    subtitle: 'A small corner of a very big universe.',
    tag: 'Made of curiosity',
    mark: 'R!',
  },
} as const;

export function DesignConcept({
  direction = 'orbital',
  graphics = 'auto',
}: {
  direction?: Direction;
  graphics?: 'auto' | 'poster';
}) {
  const copy = directions[direction];
  const reduced = useReducedMotionPreference();
  const root = useRef<HTMLDivElement>(null);
  const x = useSpring(0, { stiffness: 180, damping: 26 });
  const y = useSpring(0, { stiffness: 180, damping: 26 });
  return (
    <div
      ref={root}
      className={`design-concept concept-${direction}`}
      data-direction={direction}
    >
      <a className="skip-link" href="#concept-scene">
        Skip to the scene
      </a>
      <aside className="concept-rail" data-concept-region="navigation">
        <div className="concept-wordmark" aria-label="RoyenHeart">
          {copy.mark}
          <span aria-hidden="true">✳</span>
        </div>
        <a
          className="concept-profile"
          href="https://github.com/royenheart"
          aria-label="RoyenHeart on GitHub"
          onPointerMove={(event) => {
            if (
              direction !== 'liquid' ||
              reduced ||
              event.pointerType !== 'mouse'
            )
              return;
            const bounds = event.currentTarget.getBoundingClientRect();
            x.set((event.clientX - bounds.x - bounds.width / 2) * 0.12);
            y.set((event.clientY - bounds.y - bounds.height / 2) * 0.12);
          }}
          onPointerLeave={() => {
            x.set(0);
            y.set(0);
          }}
        >
          <motion.img
            src={avatar}
            alt="RoyenHeart's avatar"
            width={92}
            height={92}
            style={{ x, y }}
          />
        </a>
        <div className="concept-intro">
          <span>{copy.tag}</span>
          <h1>
            Royen<span>Heart</span>
          </h1>
        </div>
        <nav className="concept-links" aria-label="Personal links">
          <a href={site.links[0]!.href} target="_blank" rel="noreferrer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 4h13v16H5zM8 8h7M8 12h7M8 16h4" />
            </svg>
            <span>Blog</span>
            <span className="link-index" aria-hidden="true">
              ↗
            </span>
          </a>
          <a href={site.links[1]!.href} target="_blank" rel="noreferrer">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16" />
            </svg>
            <span>GitHub</span>
            <span className="link-index" aria-hidden="true">
              ↗
            </span>
          </a>
        </nav>
        <div className="concept-rail-note">
          <span className="concept-orbit" aria-hidden="true">
            <i />
          </span>
          <p>{copy.subtitle}</p>
          <small>RoyenHeart's home on the web</small>
        </div>
      </aside>
      <main
        className="concept-main"
        id="concept-scene"
        tabIndex={-1}
        data-concept-region="scene"
      >
        <header className="concept-scene-caption">
          <span className="caption-mark" aria-hidden="true">
            ✳
          </span>
          <div>
            <span className="caption-cubes">Blue cube cloud</span>
            <span className="caption-horizon">Golden event horizon</span>
          </div>
          <span className="caption-note">A moving canvas</span>
        </header>
        <div className="concept-viewport">
          <SceneExperience
            settings={scenes}
            posters={{ cubes, horizon }}
            graphics={graphics}
          />
          <div className="concept-scene-label" aria-hidden="true">
            <span className="caption-cubes">
              Blue
              <br />
              hours.
            </span>
            <span className="caption-horizon">
              Beyond
              <br />
              the light.
            </span>
          </div>
        </div>
        <div className="concept-scene-footnote">
          <span>Take a moment. Stay a while.</span>
          <span>Two scenes, one small universe.</span>
        </div>
      </main>
      <footer className="concept-footer" data-concept-region="footer">
        <div className="concept-player" data-concept-region="music">
          <UnifiedPlayer
            tracks={previewTracks}
            resolveTrack={resolvePreviewTrack}
          />
        </div>
        <div className="concept-legal" data-concept-region="legal">
          {site.registrations.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noreferrer"
            >
              {link.label}
            </a>
          ))}
        </div>
      </footer>
    </div>
  );
}
