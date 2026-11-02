import {
  Component,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from 'react';
import { motion, MotionConfig } from 'motion/react';
import { useReducedMotionPreference } from '../../lib/useReducedMotionPreference';
import type { SceneId, SceneSettings } from '../../lib/content/schema';
import type { SceneCanvasProps } from './SceneCanvas';

type CanvasModule = { default: ComponentType<SceneCanvasProps> };
const loadCanvas = () => import('./SceneCanvas');
export interface SceneExperienceProps {
  settings: SceneSettings;
  posters: Record<SceneId, string>;
  graphics?: 'auto' | 'poster';
  loadGraphics?: () => Promise<CanvasModule>;
}

class GraphicsBoundary extends Component<
  { children: ReactNode; onFailure: () => void },
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

export function SceneExperience({
  settings,
  posters,
  graphics = 'auto',
  loadGraphics = loadCanvas,
}: SceneExperienceProps) {
  const [scene, setScene] = useState<SceneId>(settings.defaultScene);
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(true);
  const [capture, setCapture] = useState(false);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(false);
  const [CanvasComponent, setCanvas] =
    useState<ComponentType<SceneCanvasProps> | null>(null);
  const reducedMotion = useReducedMotionPreference();
  const container = useRef<HTMLDivElement>(null);
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback(() => {
    setFailure(true);
    setReady(false);
  }, []);

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams(window.location.search);
    setCapture(query.get('capture') === '1');
    if (graphics === 'poster' || query.get('graphics') === 'poster') return;
    loadGraphics()
      .then((module) => {
        if (active) setCanvas(() => module.default);
      })
      .catch(() => {
        if (active) onFailure();
      });
    return () => {
      active = false;
    };
  }, [graphics, loadGraphics, onFailure]);

  useEffect(() => {
    let inView = true;
    const update = () =>
      setVisible(inView && document.visibilityState !== 'hidden');
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry?.isIntersecting ?? true;
      update();
    });
    if (container.current) observer.observe(container.current);
    document.addEventListener('visibilitychange', update);
    update();
    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange', update);
    };
  }, []);

  const still = paused || Boolean(reducedMotion) || !visible;
  return (
    <MotionConfig reducedMotion="user">
      <div
        ref={container}
        className="scene-experience"
        data-scene={scene}
        data-renderer={failure ? 'fallback' : ready ? 'webgl' : 'poster'}
        data-paused={still ? 'true' : 'false'}
      >
        <img
          className="scene-poster"
          src={posters[scene]}
          alt=""
          width={1321}
          height={806}
          aria-hidden="true"
          fetchPriority="high"
        />
        {CanvasComponent && !failure && (
          <motion.div
            className="scene-canvas"
            initial={{ opacity: 0 }}
            animate={{ opacity: ready ? 1 : 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.6 }}
            aria-hidden="true"
          >
            <GraphicsBoundary onFailure={onFailure}>
              <CanvasComponent
                scene={scene}
                settings={settings}
                paused={still}
                capture={capture}
                onReady={onReady}
                onFailure={onFailure}
              />
            </GraphicsBoundary>
          </motion.div>
        )}
        {ready && (
          <motion.div
            key={scene}
            className="scene-transition"
            aria-hidden="true"
            style={{
              backgroundColor:
                scene === 'cubes'
                  ? settings.cubes.background
                  : settings.horizon.background,
            }}
            initial={{ opacity: 0.8 }}
            animate={{ opacity: 0 }}
            transition={{ duration: reducedMotion || capture ? 0 : 0.65 }}
          />
        )}
        {failure && (
          <span className="scene-status" role="status">
            Still view · graphics unavailable
          </span>
        )}
        <div className="scene-toolbar" role="group" aria-label="Scene controls">
          <button
            className="scene-control"
            type="button"
            aria-label={paused ? 'Resume animation' : 'Pause animation'}
            aria-pressed={paused}
            onClick={() => setPaused((value) => !value)}
            disabled={Boolean(reducedMotion)}
            title={
              reducedMotion
                ? 'Reduced motion is enabled on your device'
                : paused
                  ? 'Resume animation'
                  : 'Pause animation'
            }
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              {paused ? (
                <path d="m8 5 10 7-10 7Z" />
              ) : (
                <path d="M8 5v14M16 5v14" />
              )}
            </svg>
          </button>
          <motion.button
            className="scene-control"
            type="button"
            aria-label="Switch scene"
            whileTap={{ scale: 0.92 }}
            onClick={() =>
              setScene((current) => (current === 'cubes' ? 'horizon' : 'cubes'))
            }
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M19 10a7.5 7.5 0 1 0 0 6M19 3v7h-7" />
            </svg>
          </motion.button>
        </div>
        <span className="sr-only" aria-live="polite">
          {scene === 'cubes' ? 'Blue cube cloud' : 'Golden event horizon'}
        </span>
      </div>
    </MotionConfig>
  );
}
