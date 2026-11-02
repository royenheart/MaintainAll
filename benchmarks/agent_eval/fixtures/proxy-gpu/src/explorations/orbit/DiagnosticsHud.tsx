import { useEffect, useRef, useState } from 'react';
import type { SceneId } from '../../lib/content/schema';

interface Snapshot {
  fps: number;
  frames: number;
  calls: number;
  buffer: string;
  dpr: number;
  quality: number;
  renderer: string;
  webgl2: boolean;
  hasCanvas: boolean;
  rendererState: string;
  failure: boolean;
  reason: string;
  software: boolean;
  scene: string;
  prepared: string;
  preparation: string;
  transitioning: string;
  queued: string;
  audioReady: string;
  audioBlocked: string;
  audioPlaying: string;
  online: string;
  visibility: string;
  connection: string;
  viewport: string;
  cores: string;
  fonts: string;
  history: number[];
}

function readCanvasRenderer() {
  const canvas = document.querySelector('canvas');
  const gl =
    canvas?.getContext('webgl2') ?? canvas?.getContext('webgl') ?? null;
  if (!gl) return { renderer: 'no canvas', webgl2: false };
  const extension = gl.getExtension('WEBGL_debug_renderer_info');
  return {
    renderer: String(
      extension
        ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL)
        : gl.getParameter(gl.RENDERER),
    ),
    webgl2:
      typeof WebGL2RenderingContext !== 'undefined' &&
      gl instanceof WebGL2RenderingContext,
  };
}

function connectionLabel() {
  const connection = (
    navigator as unknown as {
      connection?: {
        effectiveType?: string;
        downlink?: number;
        rtt?: number;
        saveData?: boolean;
      };
    }
  ).connection;
  if (!connection) return 'unknown';
  const parts = [connection.effectiveType ?? 'unknown'];
  if (typeof connection.downlink === 'number')
    parts.push(`${connection.downlink}Mb/s`);
  if (typeof connection.rtt === 'number') parts.push(`${connection.rtt}ms`);
  if (connection.saveData) parts.push('save-data');
  return parts.join(' · ');
}

const EMPTY: Snapshot = {
  fps: 0,
  frames: 0,
  calls: 0,
  buffer: '—',
  dpr: 0,
  quality: 1,
  renderer: '—',
  webgl2: false,
  hasCanvas: false,
  rendererState: '—',
  failure: false,
  reason: '—',
  software: false,
  scene: '—',
  prepared: '—',
  preparation: '—',
  transitioning: '—',
  queued: '—',
  audioReady: '—',
  audioBlocked: '—',
  audioPlaying: '—',
  online: '—',
  visibility: '—',
  connection: '—',
  viewport: '—',
  cores: '—',
  fonts: '—',
  history: [],
};

export function DiagnosticsHud({
  scene,
  quality,
  failure,
  failureReason,
  software,
}: {
  scene: SceneId;
  quality: number;
  failure: boolean;
  failureReason: string;
  software: boolean;
}) {
  const [open, setOpen] = useState(
    () =>
      new URLSearchParams(window.location.search).get('diagnostics') === '1',
  );
  const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY);
  const previous = useRef<{ frames: number; time: number } | null>(null);
  const history = useRef<number[]>([]);
  const title = scene === 'cubes' ? 'AXOLOTL' : 'EVENT HORIZON';

  useEffect(() => {
    const toggle = (event: KeyboardEvent) => {
      if (
        event.key.toLowerCase() !== 'd' ||
        !event.shiftKey ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey
      )
        return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest('input, textarea, select, [contenteditable]')
      )
        return;
      event.preventDefault();
      setOpen((value) => !value);
    };
    document.addEventListener('keydown', toggle);
    return () => document.removeEventListener('keydown', toggle);
  }, []);

  useEffect(() => {
    if (!open) return;
    const sample = () => {
      const main = document.querySelector('main');
      const metrics = window.__orbitScene;
      const now = performance.now();
      const frames = metrics?.frames ?? 0;
      let fps = 0;
      if (previous.current)
        fps =
          ((frames - previous.current.frames) * 1000) /
          Math.max(1, now - previous.current.time);
      previous.current = { frames, time: now };
      history.current.push(fps);
      if (history.current.length > 60) history.current.shift();
      const renderer = readCanvasRenderer();
      const audio = document.querySelector('.orbit-wheel');
      setSnapshot({
        fps,
        frames,
        calls: metrics?.calls ?? 0,
        buffer: metrics
          ? `${metrics.bufferWidth} × ${metrics.bufferHeight}`
          : '—',
        dpr: metrics?.pixelRatio ?? 0,
        quality,
        renderer: renderer.renderer,
        webgl2: renderer.webgl2,
        hasCanvas: Boolean(document.querySelector('canvas')),
        rendererState: main?.getAttribute('data-renderer') ?? '—',
        failure,
        reason: failureReason,
        software,
        scene: main?.getAttribute('data-scene') ?? '—',
        prepared: main?.getAttribute('data-prepared') ?? '—',
        preparation: main?.getAttribute('data-preparation') ?? '—',
        transitioning: main?.getAttribute('data-transitioning') ?? '—',
        queued: main?.getAttribute('data-navigation-queued') ?? '—',
        audioReady: main?.getAttribute('data-audio-ready') ?? '—',
        audioBlocked: main?.getAttribute('data-audio-blocked') ?? '—',
        audioPlaying: audio?.getAttribute('data-playing') ?? '—',
        online: navigator.onLine ? 'online' : 'offline',
        visibility: document.visibilityState,
        connection: connectionLabel(),
        viewport: `${innerWidth} × ${innerHeight}`,
        cores: `${navigator.hardwareConcurrency ?? '—'} threads`,
        fonts: document.fonts.status,
        history: [...history.current],
      });
    };
    sample();
    const timer = window.setInterval(sample, 500);
    return () => {
      window.clearInterval(timer);
      previous.current = null;
    };
  }, [failure, failureReason, open, quality, software]);

  const width = 240;
  const height = 46;
  const max = 80;
  const points = snapshot.history
    .map((value, index) => {
      const x =
        snapshot.history.length <= 1
          ? width
          : (index / (snapshot.history.length - 1)) * width;
      const y = height - (Math.min(max, Math.max(0, value)) / max) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <>
      <button
        type="button"
        className="orbit-diagnostics-trigger"
        aria-label="Runtime diagnostics"
        aria-controls="orbit-diagnostics"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">&gt;_</span>
      </button>
      {open && (
        <aside
          id="orbit-diagnostics"
          className="orbit-diagnostics"
          aria-label={`Runtime diagnostics for ${title}`}
          role="dialog"
          aria-modal="false"
        >
          <div className="orbit-diagnostics-head">
            <span>ORBIT // RUNTIME</span>
            <span className="orbit-diagnostics-case">{title}</span>
            <kbd>Shift+D</kbd>
            <button
              type="button"
              className="orbit-diagnostics-close"
              aria-label="Close diagnostics"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>
          <div className="orbit-diagnostics-chart" aria-hidden="true">
            <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
              <line
                x1="0"
                y1={height - (60 / max) * height}
                x2={width}
                y2={height - (60 / max) * height}
              />
              <line
                x1="0"
                y1={height - (30 / max) * height}
                x2={width}
                y2={height - (30 / max) * height}
              />
              <polyline points={points} />
            </svg>
            <span className="orbit-diagnostics-chart-label">60</span>
            <span className="orbit-diagnostics-chart-label">30</span>
          </div>
          <dl className="orbit-diagnostics-grid">
            <dt>frame</dt>
            <dd>
              {snapshot.fps.toFixed(1)} fps · {snapshot.frames} submitted
            </dd>
            <dt>buffer</dt>
            <dd>
              {snapshot.buffer} · DPR {snapshot.dpr.toFixed(2)} · q
              {snapshot.quality.toFixed(2)}
            </dd>
            <dt>draw</dt>
            <dd>{snapshot.calls} calls</dd>
            <dt>renderer</dt>
            <dd>{snapshot.renderer}</dd>
            <dt>status</dt>
            <dd>
              {snapshot.rendererState === 'fallback'
                ? 'still view'
                : snapshot.rendererState}{' '}
              · {snapshot.scene} ·{' '}
              {snapshot.transitioning === 'true' ? 'transition' : 'settled'}
            </dd>
            <dt>optics</dt>
            <dd>
              {snapshot.prepared} · {snapshot.preparation} · queued{' '}
              {snapshot.queued}
            </dd>
            <dt>audio</dt>
            <dd>
              {snapshot.audioPlaying === 'true' ? 'playing' : 'idle'} · ready{' '}
              {snapshot.audioReady} · blocked {snapshot.audioBlocked}
            </dd>
            <dt>browser</dt>
            <dd>
              {snapshot.online} · {snapshot.visibility} · {snapshot.connection}
            </dd>
            <dt>device</dt>
            <dd>
              {snapshot.viewport} · {snapshot.cores} · {snapshot.fonts} fonts
            </dd>
            <dt>webgl</dt>
            <dd>
              {snapshot.webgl2 ? 'webgl2' : 'webgl1/unknown'}
              {snapshot.software ? ' · software renderer' : ' · hardware'}
            </dd>
            {snapshot.failure && (
              <>
                <dt>fault</dt>
                <dd className="orbit-diagnostics-fault">{snapshot.reason}</dd>
              </>
            )}
          </dl>
          <p className="orbit-diagnostics-foot">
            Local only · no telemetry · Shift+D / × closes
          </p>
        </aside>
      )}
    </>
  );
}
