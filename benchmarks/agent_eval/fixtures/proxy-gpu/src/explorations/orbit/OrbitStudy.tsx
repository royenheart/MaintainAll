import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import {
  animate,
  AnimatePresence,
  motion,
  MotionConfig,
  useMotionValue,
  useIsPresent,
  useTransform,
  type AnimationPlaybackControls,
} from 'motion/react';
import { site } from '../../lib/content/load';
import type { SceneId, SiteContent } from '../../lib/content/schema';
import { useReducedMotionPreference } from '../../lib/useReducedMotionPreference';
import type { TrackResolver } from '../../lib/music/sources';
import { resolvePublicAudio } from '../../lib/music/sources';
import { sceneTracks, type SceneTracks } from '../../lib/music/scene-tracks';
import avatar from '../../assets/avatar.webp?url';
import cubesPoster from '../../assets/cubes.webp?url';
import horizonPoster from '../../assets/horizon-selected.webp?url';
import { formationTiming } from './formation';
import { AudioWheel } from './AudioWheel';
import { DamageField } from './DamageField';
import { DiagnosticsHud } from './DiagnosticsHud';
import { continuousCards, sceneTitles } from './ContinuousCards';
import {
  randomCoverStudy,
  type FontStudy,
  type CoverStudy,
  type CoverSelection,
  type IdentityStudy,
  type DetailStudy,
} from './presentation';
import { RegistrationLinks } from './RegistrationLinks';
import { useAutoplayRecovery } from './useAutoplayRecovery';
import type { RailStudy } from './ElsewhereRails';
import type {
  CardFinish,
  SurfaceMotion,
  ElsewhereStudy,
  CardExtraction,
  CardMaterial,
  CardArtSelection,
  ElsewhereMark,
} from './card-finishes';
import { CardDeck, type OrbitCard } from './CardDeck';
import { RotaryDeck } from './RotaryDeck';
import type { DockDesign } from './rotary-designs';
import { useOrbitSoundtrack } from './useOrbitSoundtrack';
import {
  adjacentScene,
  motionStudies,
  randomScene,
  sceneBlend,
  type MotionStudy,
} from './sequence';
import '@fontsource/space-grotesk/400.css';
import '@fontsource/space-grotesk/500.css';
import '@fontsource/instrument-serif/400.css';
import './orbit.css';
import './rotary.css';
import './presentation.css';
import './detail-studies.css';
import './rails.css';
import './card-finishes.css';
import './nameplate-motion.css';
import './elsewhere-preview.css';
import './damage.css';
import './diagnostics.css';
import type {
  DiskStyle,
  HorizonDiagnostic,
} from '../../scenes/RelativisticHorizon';
import type { HorizonTreatment } from '../../scenes/relativity/framing';

const OrbitCanvas = lazy(() => import('./OrbitCanvas'));
const titles = sceneTitles;
const posters = { cubes: cubesPoster, horizon: horizonPoster };
const timestamp = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, '0')}`;
class GraphicsBoundary extends Component<
  { children: ReactNode; onFailure(): void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onFailure();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function ArrivalVeil({
  forming,
  reduced,
  children,
}: {
  forming: boolean;
  reduced: boolean;
  children: ReactNode;
}) {
  const present = useIsPresent();
  return (
    <motion.section
      initial={false}
      exit={{ opacity: 0, pointerEvents: 'none' }}
      transition={{ duration: reduced ? 0 : 0.6 }}
      inert={!present}
      className="orbit-arrival"
      data-forming={forming}
      aria-label="Enter the scene"
    >
      {children}
    </motion.section>
  );
}

export interface OrbitStudyProps {
  interfaceMode?: 'legacy' | 'continuous';
  fontStudy?: FontStudy;
  coverStudy?: CoverSelection;
  identityStudy?: IdentityStudy;
  detailStudy?: DetailStudy;
  railStudy?: RailStudy;
  cardFinish?: CardFinish;
  surfaceMotion?: SurfaceMotion;
  elsewhereStudy?: ElsewhereStudy;
  elsewhereLinks?: SiteContent['links'];
  cardExtraction?: CardExtraction;
  cardMaterial?: CardMaterial;
  cardArt?: CardArtSelection;
  elsewhereMark?: ElsewhereMark;
  initialCard?: 'identity' | 'music' | 'elsewhere' | 'next';
  study?: MotionStudy;
  initialScene?: SceneId;
  graphics?: 'auto' | 'poster';
  skipEntrance?: boolean;
  startOpen?: boolean;
  resolve?: TrackResolver;
  tracks?: SceneTracks;
  horizonRenderer?: 'baseline' | 'relativistic';
  diskStyle?: DiskStyle;
  inclination?: number;
  bloom?: number;
  dockDesign?: DockDesign;
  cardDuration?: number;
  horizonTreatment?: HorizonTreatment;
  horizonDiagnostic?: HorizonDiagnostic;
  ruptureStyle?: 'material' | 'mirror' | 'glitch';
}

export function OrbitStudy({
  interfaceMode = 'legacy',
  fontStudy = 'plex',
  coverStudy = 'random',
  identityStudy = 'orbit',
  detailStudy,
  railStudy = 'glide',
  cardFinish = interfaceMode === 'continuous' ? 'nameplate' : 'original',
  surfaceMotion = 'drift',
  elsewhereStudy = 'tile',
  elsewhereLinks = site.links,
  cardExtraction = 'slide',
  cardMaterial = 'drift',
  cardArt = 'scene',
  elsewhereMark = 'editorial',
  initialCard = 'identity',
  study = 'collapse',
  initialScene,
  graphics = 'auto',
  skipEntrance = false,
  startOpen = false,
  resolve = resolvePublicAudio,
  tracks = sceneTracks,
  horizonRenderer = 'relativistic',
  diskStyle = 'turbulent',
  inclination = 12,
  bloom = 0.28,
  dockDesign = 'drum',
  cardDuration = 0.68,
  horizonTreatment = 'limb',
  horizonDiagnostic = 'beauty',
  ruptureStyle = 'glitch',
}: OrbitStudyProps) {
  const continuous = interfaceMode === 'continuous';
  const [scene, setScene] = useState<SceneId>(
    () => initialScene ?? randomScene(),
  );
  const [entered, setEntered] = useState(skipEntrance || continuous);
  const [expanded, setExpanded] = useState(
    continuous || (startOpen && skipEntrance),
  );
  const [index, setIndex] = useState(() =>
    interfaceMode === 'continuous'
      ? ['identity', 'music', 'elsewhere', 'next'].indexOf(initialCard)
      : 0,
  );
  const [busy, setBusy] = useState(false);
  const [transitionCover, setTransitionCover] = useState<CoverStudy>('ripple');
  const [targetScene, setTargetScene] = useState<SceneId | null>(null);
  const [graphicsReady, setGraphicsReady] = useState(graphics === 'poster');
  // Poster and failed-graphics paths navigate static artwork and never mount the
  // canvas that would otherwise report optical preparation.
  const [prepared, setPrepared] = useState(graphics === 'poster');
  const [preparationSlow, setPreparationSlow] = useState(false);
  const [failure, setFailure] = useState(false);
  const [introDone, setIntroDone] = useState(skipEntrance);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(true);
  const [capture] = useState(
    () =>
      typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('capture') === '1',
  );
  const reduced = useReducedMotionPreference();
  const choreography =
    horizonRenderer === 'relativistic' && horizonTreatment === 'limb';
  const blend = useMotionValue(sceneBlend(scene));
  const entrance = useMotionValue(skipEntrance ? 1 : 0);
  const direction = useMotionValue(1);
  const accent = useTransform(blend, [0, 1], ['#94dfff', '#f5cc84']);
  const glow = useTransform(blend, [0, 1], ['#527eb933', '#b8813833']);
  const transition = useRef<AnimationPlaybackControls | null>(null);
  const locked = useRef(false);
  const root = useRef<HTMLElement>(null);
  const ignoreFocus = useRef(false);
  const restoreDeckFocus = useRef(false);
  const focusArtwork = useRef(false);
  const pendingNavigation = useRef<1 | -1 | null>(null);
  const [queuedScene, setQueuedScene] = useState(false);
  const [graphicsSlow, setGraphicsSlow] = useState(false);
  const [failureReason, setFailureReason] = useState('unknown');
  const [softwareRenderer, setSoftwareRenderer] = useState(false);
  const [quality, setQuality] = useState(1);
  const onReady = useCallback(() => setGraphicsReady(true), []);
  const onQuality = useCallback((value: number) => setQuality(value), []);
  const onPrepared = useCallback(() => setPrepared(true), []);
  // The selected continuous page starts the horizon tables as soon as the
  // island hydrates. Waiting for the cube arrival only pushes the expensive
  // destination preparation behind the user's first scene switch.
  const prepareHorizon = continuous || scene === 'horizon' || introDone;
  const degraded = failure || softwareRenderer || quality < 0.75;
  const damageSeverity = failure
    ? 'fault'
    : quality <= 0.5 || softwareRenderer
      ? 'high'
      : 'low';
  const onFailure = useCallback((reason = 'unknown') => {
    console.warn(`[orbit] falling back to still view: ${reason}`);
    setFailureReason(reason);
    setFailure(true);
    setGraphicsReady(true);
    setPrepared(true);
  }, []);
  const onSoftware = useCallback(() => setSoftwareRenderer(true), []);
  const next = useRef<() => void>(() => {});
  const audio = useOrbitSoundtrack(
    tracks,
    resolve,
    scene,
    targetScene,
    blend,
    visible,
    () => next.current(),
  );
  const { pause, play } = audio;
  const navigate = useCallback(
    (step: 1 | -1) => {
      if (locked.current || !entered || !introDone) return;
      const target = adjacentScene(scene, step);
      // Do not start a horizon transition until its optical tables and reverse
      // presentation material are prepared. Queue the intent instead of making
      // the visible scene control a silent no-op.
      if (target === 'horizon' && !prepared) {
        pendingNavigation.current = step;
        setQueuedScene(true);
        return;
      }
      pendingNavigation.current = null;
      setQueuedScene(false);
      locked.current = true;
      focusArtwork.current = false;
      restoreDeckFocus.current =
        continuous &&
        Boolean(
          root.current
            ?.querySelector('.orbit-dock')
            ?.contains(document.activeElement),
        );
      setTransitionCover(
        coverStudy === 'random' ? randomCoverStudy() : coverStudy,
      );
      setBusy(true);
      if (!continuous) setExpanded(false);
      setTargetScene(target);
      direction.set(scene === 'cubes' ? 1 : -1);
      transition.current?.stop();
      transition.current = animate(blend, sceneBlend(target), {
        duration: reduced
          ? 0
          : failure || graphics === 'poster'
            ? 0.2
            : choreography
              ? study === 'collapse'
                ? formationTiming[
                    scene === 'cubes'
                      ? 'collapse'
                      : ruptureStyle === 'glitch'
                        ? 'glitch'
                        : ruptureStyle === 'mirror'
                          ? 'mirror'
                          : 'rupture'
                  ]
                : formationTiming.transition
              : motionStudies[study].duration,
        ease: choreography ? 'linear' : [0.65, 0, 0.35, 1],
        onComplete: () => {
          setScene(target);
          setIndex(0);
          setTargetScene(null);
          locked.current = false;
          setBusy(false);
        },
      });
    },
    [
      blend,
      continuous,
      coverStudy,
      introDone,
      entered,
      failure,
      graphics,
      reduced,
      scene,
      study,
      choreography,
      direction,
      prepared,
      ruptureStyle,
    ],
  );
  useEffect(() => {
    next.current = () => navigate(1);
  }, [navigate]);
  useEffect(() => {
    if (
      !prepared ||
      busy ||
      locked.current ||
      pendingNavigation.current === null
    )
      return;
    const step = pendingNavigation.current;
    pendingNavigation.current = null;
    setQueuedScene(false);
    navigate(step);
  }, [busy, navigate, prepared]);
  useEffect(() => {
    if (!busy) return;
    // The dock becomes inert while a scene changes. If the visitor moves focus
    // or clicks outside it, do not steal focus back when the transition ends.
    const release = (event: Event) => {
      const dock = root.current?.querySelector('.orbit-dock');
      const target = event.target;
      if (!(target instanceof Node) || !dock?.contains(target)) {
        restoreDeckFocus.current = false;
        focusArtwork.current = false;
        ignoreFocus.current = false;
      }
    };
    const refocus = (event: FocusEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target !== document.body)
        release(event);
    };
    document.addEventListener('pointerdown', release, true);
    document.addEventListener('keydown', release, true);
    document.addEventListener('focusin', refocus, true);
    return () => {
      document.removeEventListener('pointerdown', release, true);
      document.removeEventListener('keydown', release, true);
      document.removeEventListener('focusin', refocus, true);
    };
  }, [busy]);
  useEffect(() => {
    if (busy) return;
    if (restoreDeckFocus.current) {
      restoreDeckFocus.current = false;
      root.current?.querySelector<HTMLElement>('.rotary-deck')?.focus();
      return;
    }
    if (!focusArtwork.current) return;
    focusArtwork.current = false;
    ignoreFocus.current = true;
    root.current?.querySelector<HTMLButtonElement>('.orbit-disc')?.focus();
    queueMicrotask(() => {
      ignoreFocus.current = false;
    });
  }, [busy, scene]);
  useEffect(
    () => () => {
      transition.current?.stop();
    },
    [],
  );
  useEffect(() => {
    // Reduced motion can be enabled after a transition has started. Motion does
    // not observe the React preference for this imperative animation, so settle
    // the handoff immediately instead of leaving the dock inert for seconds.
    if (!reduced || !busy || !targetScene) return;
    transition.current?.stop();
    transition.current = null;
    blend.set(sceneBlend(targetScene));
    setScene(targetScene);
    setIndex(0);
    setTargetScene(null);
    locked.current = false;
    setBusy(false);
  }, [blend, busy, reduced, targetScene]);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', update);
    update();
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  useEffect(() => {
    if (graphicsReady || graphics === 'poster') return;
    setGraphicsSlow(false);
    const slow = window.setTimeout(() => setGraphicsSlow(true), 8000);
    // Slow initialization is not an unavailable renderer. Explicit optical,
    // shader, context and source failures still call onFailure; a pending
    // fetch or driver compile must not turn the first horizon visit into the
    // damaged fallback.
    return () => clearTimeout(slow);
  }, [graphics, graphicsReady]);
  useEffect(() => {
    // A cube-first scene can be interactive while the horizon is still
    // preparing. Never turn a slow destination into a global renderer failure:
    // keep the working cubes alive and let preparation finish or remain gated.
    if (graphics !== 'auto' || prepared || failure || !introDone) return;
    const timeout = window.setTimeout(() => setPreparationSlow(true), 15000);
    return () => clearTimeout(timeout);
  }, [failure, graphics, introDone, prepared]);
  useEffect(() => {
    if (!graphicsReady || introDone) return;
    const control = animate(entrance, 1, {
      duration:
        reduced || failure || graphics === 'poster'
          ? 0
          : choreography
            ? formationTiming[scene]
            : scene === 'cubes'
              ? 2.2
              : 2.8,
      ease: choreography ? 'linear' : [0.22, 1, 0.36, 1],
      onComplete: () => setIntroDone(true),
    });
    return () => control.stop();
  }, [
    entrance,
    failure,
    graphics,
    graphicsReady,
    introDone,
    reduced,
    scene,
    choreography,
  ]);
  const close = useCallback(() => {
    if (!continuous) setExpanded(false);
    pendingNavigation.current = null;
    setQueuedScene(false);
    restoreDeckFocus.current = false;
    if (busy) {
      // The artwork control is inert during a transition; defer the focus move
      // instead of dropping it on the document body.
      focusArtwork.current = true;
      ignoreFocus.current = true;
      return;
    }
    ignoreFocus.current = true;
    root.current?.querySelector<HTMLButtonElement>('.orbit-disc')?.focus();
    queueMicrotask(() => {
      ignoreFocus.current = false;
    });
  }, [busy, continuous]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      event.preventDefault();
      close();
    };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [close]);
  const toggleSound = () => {
    // Use the requested state, not the media element's audible state: a
    // buffering deck reports playing=false while its play intent is still live.
    if (audio.wanted) {
      pause();
    } else {
      void play();
    }
  };
  const enter = (sound: boolean) => {
    if (sound) void play();
    setEntered(true);
  };
  const legacyCards: OrbitCard[] = [
    {
      id: 'identity',
      label: 'A little about me',
      content: (
        <div className="orbit-ribbon-copy orbit-profile">
          <img
            src={avatar}
            alt={`${site.name}'s avatar`}
            width="32"
            height="32"
          />
          <h2 title={site.name}>{site.name}</h2>
        </div>
      ),
    },
    {
      id: 'scene',
      label: 'Inside this scene',
      content: (
        <>
          <div className="orbit-ribbon-copy">
            <p className="orbit-eyebrow">This scene</p>
            <h2 title={titles[scene]}>{titles[scene]}</h2>
          </div>
          <button
            className="orbit-ribbon-action"
            aria-label={paused ? 'Resume background' : 'Pause background'}
            onClick={() => setPaused((value) => !value)}
            disabled={reduced || failure || graphics === 'poster'}
          >
            {paused ? '▷' : 'Ⅱ'}
          </button>
        </>
      ),
    },
    {
      id: 'music',
      label: 'On the turntable',
      content: (
        <>
          <div className="orbit-ribbon-copy">
            <p className="orbit-eyebrow" title={tracks[scene].artist}>
              {tracks[scene].artist}
            </p>
            <h2 title={tracks[scene].title}>{tracks[scene].title}</h2>
          </div>
          <progress
            className="orbit-ribbon-progress"
            max={audio.duration || tracks[scene].duration || 1}
            value={audio.time}
            aria-label={`Song progress: ${timestamp(audio.time)}`}
          />
        </>
      ),
    },
    ...(tracks[scene].links ?? []).map((link) => ({
      id: `source-${link.label}`,
      label: `Listen on ${link.label}`,
      content: (
        <a
          className="orbit-ribbon-link"
          href={link.href}
          aria-label={`Open on ${link.label}`}
        >
          <div className="orbit-ribbon-copy">
            <p className="orbit-eyebrow">Listen on</p>
            <h2>{link.label}</h2>
          </div>
          <span aria-hidden="true">↗</span>
        </a>
      ),
    })),
    ...site.links.map((link) => ({
      id: `profile-${link.label}`,
      label: link.label,
      content: (
        <a
          className="orbit-ribbon-link"
          href={link.href}
          aria-label={link.label}
        >
          <div className="orbit-ribbon-copy">
            <p className="orbit-eyebrow">Elsewhere</p>
            <h2>{link.label}</h2>
          </div>
          <span aria-hidden="true">↗</span>
        </a>
      ),
    })),
    {
      id: 'next',
      label: 'Beyond this scene',
      content: (
        <>
          <div className="orbit-ribbon-copy orbit-destination">
            <p className="orbit-eyebrow">Up next</p>
            <h2>{titles[adjacentScene(scene, 1)]}</h2>
          </div>
          <div className="orbit-scene-actions">
            <button
              className="orbit-ribbon-action"
              aria-label="Previous scene"
              title="Previous scene"
              onClick={() => navigate(-1)}
              disabled={busy}
            >
              ←
            </button>
            <button
              className="orbit-ribbon-action"
              aria-label="Next scene"
              title="Next scene"
              onClick={() => navigate(1)}
              disabled={busy}
            >
              →
            </button>
          </div>
        </>
      ),
    },
  ];
  const cards = continuous
    ? continuousCards({
        scene,
        track: tracks[scene],
        identity: identityStudy,
        railStudy,
        cardFinish,
        elsewhereStudy,
        elsewhereLinks,
        cardExtraction,
        cardMaterial,
        cardArt:
          cardArt === 'scene'
            ? scene === 'horizon'
              ? 'relief'
              : 'foil'
            : cardArt,
        elsewhereMark,
        reduced,
        time: audio.time,
        duration: audio.duration,
        playing: audio.wanted,
        ready: audio.ready && !busy,
        sceneReady: scene === 'horizon' || prepared,
        navigationQueued: queuedScene,
        onSound: toggleSound,
        onPrevious: () => navigate(-1),
        onNext: () => navigate(1),
      })
    : legacyCards;
  const autoplayAttempted = useRef(false);
  const { autoplay } = audio;
  useAutoplayRecovery(
    continuous && introDone && !busy,
    audio.blocked,
    autoplay,
  );
  useEffect(() => {
    if (!continuous || !introDone || !audio.ready || autoplayAttempted.current)
      return;
    autoplayAttempted.current = true;
    if (!audio.playing) void autoplay();
  }, [continuous, introDone, audio.ready, audio.playing, autoplay]);
  return (
    <MotionConfig reducedMotion="user">
      <motion.main
        ref={root}
        className="orbit-study"
        data-scene={scene}
        data-interface={interfaceMode}
        data-font={fontStudy}
        data-details={detailStudy ?? (continuous ? 'flow' : 'none')}
        data-card-finish={cardFinish}
        data-surface-motion={surfaceMotion}
        data-elsewhere={elsewhereStudy}
        data-detail-motion={reduced || !visible ? 'off' : 'on'}
        data-cover-selection={coverStudy}
        data-study={study}
        data-accretion-style="orbit"
        data-dock-design={dockDesign}
        data-horizon-treatment={horizonTreatment}
        data-entered={entered}
        data-intro-done={introDone}
        data-prepared={prepared}
        data-preparation={
          prepared ? 'ready' : preparationSlow ? 'slow' : 'preparing'
        }
        data-navigation-queued={queuedScene}
        data-graphics-slow={graphicsSlow}
        data-software-renderer={softwareRenderer}
        data-degraded={degraded}
        data-damage-severity={damageSeverity}
        data-failure-reason={failureReason}
        aria-keyshortcuts="Shift+D"
        data-choreography={choreography}
        data-transitioning={busy}
        data-renderer={
          failure
            ? 'fallback'
            : graphics === 'poster'
              ? 'poster'
              : graphicsReady
                ? 'webgl'
                : 'loading'
        }
        data-reduced={reduced}
        data-audio-ready={audio.ready}
        data-audio-blocked={audio.blocked}
        style={
          {
            '--orbit-accent': accent,
            '--orbit-glow': glow,
          } as unknown as CSSProperties
        }
      >
        <div className="orbit-background" aria-hidden="true">
          <img className="orbit-poster" src={posters[scene]} alt="" />
          {graphics === 'auto' && !failure && (
            <div className="orbit-webgl">
              <GraphicsBoundary onFailure={onFailure}>
                <Suspense fallback={null}>
                  <OrbitCanvas
                    blend={blend}
                    entrance={entrance}
                    direction={direction}
                    ruptureStyle={ruptureStyle}
                    study={study}
                    capture={capture}
                    paused={paused || reduced || !visible}
                    onReady={onReady}
                    onPrepared={onPrepared}
                    onSoftware={onSoftware}
                    onQuality={onQuality}
                    prepareHorizon={prepareHorizon}
                    onFailure={onFailure}
                    horizonRenderer={horizonRenderer}
                    diskStyle={diskStyle}
                    inclination={inclination}
                    bloom={bloom}
                    horizonTreatment={horizonTreatment}
                    horizonDiagnostic={horizonDiagnostic}
                  />
                </Suspense>
              </GraphicsBoundary>
            </div>
          )}
        </div>
        <DamageField
          scene={scene}
          active={degraded}
          severity={damageSeverity}
        />
        <header className="orbit-heading">
          <h1 className="sr-only">{titles[scene]}</h1>
          {!continuous && (
            <span className="orbit-scene-number">
              {scene === 'cubes' ? '01' : '02'} <span>/ 02</span>
            </span>
          )}
        </header>
        <AnimatePresence>
          {!entered && (
            <ArrivalVeil forming={!introDone} reduced={reduced}>
              <div
                className={`orbit-arrival-mark orbit-arrival-${scene}`}
                aria-hidden="true"
              >
                <i />
                <i />
                <i />
              </div>
              <p className="orbit-eyebrow">
                {scene === 'cubes'
                  ? 'Finding a little order'
                  : 'Following the last light'}
              </p>
              <h2>{titles[scene]}</h2>
              <p role="status">
                {!introDone
                  ? 'Forming your space…'
                  : audio.ready
                    ? 'Your space is ready.'
                    : (audio.error ?? 'Preparing the music…')}
              </p>
              <button
                className="orbit-enter"
                onClick={() => enter(true)}
                disabled={!introDone || !audio.ready}
              >
                Enter with sound <span aria-hidden="true">↗</span>
              </button>
              <button
                className="orbit-quiet"
                onClick={() => enter(false)}
                disabled={!introDone}
              >
                Enter quietly
              </button>
            </ArrivalVeil>
          )}
        </AnimatePresence>
        {entered && (!continuous || introDone) && (
          <>
            <motion.div
              className="orbit-dock"
              initial={{ opacity: 0, y: reduced ? 0 : 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduced ? 0 : 0.7 }}
              inert={busy}
            >
              <div className="orbit-wheel-anchor" inert={busy}>
                <AudioWheel
                  persistent={continuous}
                  covers={continuous ? tracks : undefined}
                  blend={blend}
                  coverStudy={
                    coverStudy === 'random' ? transitionCover : coverStudy
                  }
                  playbackControl={!continuous}
                  artwork={tracks[scene].artwork}
                  title={tracks[scene].title}
                  expanded={expanded}
                  playing={audio.playing}
                  reduced={reduced || !visible}
                  scene={scene}
                  ready={audio.ready && !busy}
                  analyser={audio.analyser}
                  design={dockDesign}
                  cardIndex={index}
                  cardDuration={cardDuration}
                  onToggle={() => {
                    if (continuous) {
                      setIndex(0);
                      root.current
                        ?.querySelector<HTMLElement>('.rotary-deck')
                        ?.focus();
                    } else setExpanded((value) => !value);
                  }}
                  onFocus={() => {
                    if (!ignoreFocus.current) setExpanded(true);
                  }}
                  onSound={toggleSound}
                />
              </div>
              {expanded &&
                (continuous || !busy) &&
                dockDesign === 'classic' && (
                  <CardDeck
                    cards={cards}
                    index={index}
                    onIndex={setIndex}
                    reduced={reduced}
                    onClose={close}
                  />
                )}
              {expanded &&
                (continuous || !busy) &&
                dockDesign !== 'classic' && (
                  <RotaryDeck
                    cards={cards}
                    index={index}
                    onIndex={setIndex}
                    reduced={reduced}
                    onClose={close}
                    design={dockDesign}
                    persistent={continuous}
                    finish={cardFinish}
                    duration={cardDuration}
                  />
                )}
              {continuous && <RegistrationLinks docked />}
            </motion.div>
            {audio.error && (
              <p className="sr-only" role="status">
                {audio.error}
              </p>
            )}
          </>
        )}
        {!continuous && <RegistrationLinks />}
        <p className="sr-only" aria-live="polite">
          {busy ? 'Moving to the adjacent scene' : titles[scene]}
        </p>
        <p className="sr-only">Press Shift+D for runtime diagnostics.</p>
        <p id="orbit-preparation-status" className="sr-only" role="status">
          {graphics === 'auto' && !failure && !prepared
            ? queuedScene
              ? 'Your scene switch will begin as soon as the next scene is ready.'
              : preparationSlow
                ? 'The next scene is still preparing. You can keep exploring this scene.'
                : 'Preparing the next scene'
            : ''}
        </p>
        <DiagnosticsHud
          scene={scene}
          quality={quality}
          failure={failure}
          failureReason={failureReason}
          software={softwareRenderer}
        />
        {failure && (
          <p className="sr-only" role="status">
            {softwareRenderer
              ? 'Still view · software rendering unavailable'
              : 'Still view · graphics unavailable'}
          </p>
        )}
      </motion.main>
    </MotionConfig>
  );
}
