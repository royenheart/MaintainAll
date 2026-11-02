import { site } from '../../lib/content/load';
import avatar from '../../assets/avatar.webp?url';
import type { SceneId, SiteContent } from '../../lib/content/schema';
import type { SceneTracks } from '../../lib/music/scene-tracks';
import type { OrbitCard } from './CardDeck';
import type { IdentityStudy } from './presentation';
import { DockIcon } from './DockIcon';
import { ElsewhereRails, type RailStudy } from './ElsewhereRails';
import { ElsewhereSegments } from './ElsewhereSegments';
import { useEffect, useRef } from 'react';
import {
  animate,
  motion,
  useMotionValue,
  type AnimationPlaybackControls,
} from 'motion/react';
import type {
  CardFinish,
  ElsewhereStudy,
  CardExtraction,
  CardMaterial,
  CardArtStudy,
  ElsewhereMark,
} from './card-finishes';

export const sceneTitles = { cubes: 'Axolotl', horizon: 'Event horizon' };

function MusicSourceLink({
  label,
  href,
  reduced,
}: {
  label: string;
  href: string;
  reduced: boolean;
}) {
  const rotation = useMotionValue(0);
  const turn = useRef<AnimationPlaybackControls | null>(null);
  const spin = () => {
    if (reduced || turn.current?.state === 'running') return;
    rotation.set(0);
    turn.current = animate(rotation, 360, {
      duration: 0.7,
      ease: [0.22, 0.72, 0.18, 1],
    });
  };
  useEffect(() => {
    if (reduced) {
      turn.current?.stop();
      rotation.set(0);
    }
    return () => {
      turn.current?.stop();
    };
  }, [reduced, rotation]);
  return (
    <a
      href={href}
      aria-label={`Open on ${label}`}
      onPointerEnter={(event) => {
        if (event.pointerType !== 'touch') spin();
      }}
      onFocus={(event) => {
        if (event.currentTarget.matches(':focus-visible')) spin();
      }}
    >
      <motion.svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="orbit-source-icon"
        style={{ rotate: rotation }}
      >
        {label === 'Spotify' ? (
          <>
            <circle pathLength="1" cx="12" cy="12" r="9" />
            <path
              pathLength="1"
              d="M6.5 9q6-2.5 11 1M7.5 12q5-2 9 1M8.5 15q3.5-1.5 7 1"
            />
          </>
        ) : label === 'NetEase' ? (
          <>
            <path
              pathLength="1"
              d="M14 5c-5-2-9 2-9 7a7 7 0 1 0 13-3M14 5l-2 7a3 3 0 1 1-3-3"
            />
          </>
        ) : (
          <path
            pathLength="1"
            d="M10 14l4-4M8 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"
          />
        )}
      </motion.svg>
    </a>
  );
}

export function continuousCards({
  scene,
  track,
  identity,
  railStudy,
  cardFinish,
  elsewhereStudy,
  elsewhereLinks,
  cardExtraction,
  cardMaterial,
  cardArt,
  elsewhereMark,
  reduced,
  time,
  duration,
  playing,
  ready,
  sceneReady = true,
  navigationQueued = false,
  onSound,
  onPrevious,
  onNext,
}: {
  scene: SceneId;
  track: SceneTracks['cubes'];
  identity: IdentityStudy;
  railStudy: RailStudy;
  cardFinish: CardFinish;
  elsewhereStudy: ElsewhereStudy;
  elsewhereLinks: SiteContent['links'];
  cardExtraction: CardExtraction;
  cardMaterial: CardMaterial;
  cardArt: CardArtStudy;
  elsewhereMark: ElsewhereMark;
  reduced: boolean;
  time: number;
  duration: number;
  playing: boolean;
  ready: boolean;
  sceneReady?: boolean;
  navigationQueued?: boolean;
  onSound(): void;
  onPrevious(): void;
  onNext(): void;
}): OrbitCard[] {
  return [
    {
      id: 'identity',
      label: `${site.name} on ${sceneTitles[scene]}`,
      content: (
        <div
          className="orbit-ribbon-copy orbit-profile"
          data-identity={identity}
        >
          <img
            src={avatar}
            alt={`${site.name}'s avatar`}
            width="32"
            height="32"
          />
          <div className="orbit-person">
            <h2 title={site.name}>{site.name}</h2>
            <p className="orbit-location" title={`On ${sceneTitles[scene]}`}>
              <span className="sr-only">on </span>
              <span
                className={`orbit-connector connector-${identity}`}
                aria-hidden="true"
              >
                {identity === 'badge' ? 'on' : identity === 'route' ? '↳' : '◉'}
              </span>
              <span>{sceneTitles[scene]}</span>
            </p>
          </div>
        </div>
      ),
    },
    {
      id: 'music',
      label: 'On the turntable',
      content: (
        <>
          <div className="orbit-ribbon-copy orbit-track-copy">
            <p className="orbit-eyebrow" title={track.artist}>
              {track.artist}
            </p>
            <h2 title={track.title}>{track.title}</h2>
          </div>
          <nav className="orbit-source-links" aria-label="Music platforms">
            {(track.links ?? []).map((link) => (
              <MusicSourceLink
                key={link.href}
                href={link.href}
                label={link.label}
                reduced={reduced}
              />
            ))}
          </nav>
          <progress
            className="orbit-ribbon-progress"
            max={duration || track.duration || 1}
            value={time}
            aria-label="Song progress"
          />
        </>
      ),
    },
    {
      id: 'elsewhere',
      label: 'Elsewhere',
      boundCards:
        cardFinish === 'original'
          ? undefined
          : elsewhereLinks
              .filter((link) => link.preview)
              .map((link) => link.href),
      content:
        cardFinish === 'original' ? (
          <ElsewhereRails study={railStudy} />
        ) : (
          <ElsewhereSegments
            links={elsewhereLinks}
            study={elsewhereStudy}
            extraction={cardExtraction}
            material={cardMaterial}
            art={cardArt}
            mark={elsewhereMark}
            scene={scene}
            reduced={reduced}
          />
        ),
    },
    {
      id: 'next',
      label: 'Beyond this scene',
      content: (
        <>
          <div className="orbit-ribbon-copy orbit-destination">
            <p className="orbit-eyebrow">Up next</p>
            <h2>{sceneTitles[scene === 'cubes' ? 'horizon' : 'cubes']}</h2>
            {!sceneReady && (
              <p className="orbit-eyebrow orbit-preparation-note" role="status">
                {navigationQueued
                  ? 'Switch queued — preparing…'
                  : 'Preparing the next scene…'}
              </p>
            )}
          </div>
          <div
            className="orbit-scene-actions orbit-transport"
            role="group"
            aria-label="Music and scene controls"
          >
            <button
              className="orbit-ribbon-action"
              aria-label="Previous scene"
              aria-describedby={
                !sceneReady ? 'orbit-preparation-status' : undefined
              }
              aria-busy={!sceneReady}
              data-scene-ready={sceneReady}
              onClick={onPrevious}
            >
              <DockIcon name="previous" />
            </button>
            <button
              className="orbit-ribbon-action orbit-transport-sound"
              aria-label={playing ? 'Pause music' : 'Play music'}
              disabled={!ready}
              onClick={onSound}
            >
              <DockIcon name={playing ? 'pause' : 'play'} />
            </button>
            <button
              className="orbit-ribbon-action"
              aria-label="Next scene"
              aria-describedby={
                !sceneReady ? 'orbit-preparation-status' : undefined
              }
              aria-busy={!sceneReady}
              data-scene-ready={sceneReady}
              onClick={onNext}
            >
              <DockIcon name="next" />
            </button>
          </div>
        </>
      ),
    },
  ];
}
