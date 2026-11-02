import {
  Suspense,
  lazy,
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei/core/PerformanceMonitor';
import {
  ACESFilmicToneMapping,
  SRGBColorSpace,
  MathUtils,
  type Texture,
} from 'three';
import type { AccretionStyle, CubeArrivalStyle } from '../../scenes/accretion';
import type { GlitchDiagnostic } from '../../scenes/glitch';
import type { MotionValue } from 'motion/react';
import {
  Bloom,
  EffectComposer,
  EffectGroup,
  ToneMapping,
} from '@react-three/postprocessing';
import {
  BlendFunction,
  ToneMappingMode,
  type BloomEffect,
  type ToneMappingEffect,
  type EffectPass,
} from 'postprocessing';
import { SceneImpulse } from '../../scenes/SceneImpulse';
import { RadiationField } from '../../scenes/RadiationField';
import { CubeCloud } from '../../scenes/CubeCloud';
import {
  RelativisticHorizon,
  type DiskStyle,
  type HorizonDiagnostic,
  type RuptureStyle,
} from '../../scenes/RelativisticHorizon';
import { scenes } from '../../lib/content/load';
import { motionStudies, type MotionStudy } from './sequence';
import type { HorizonTreatment } from '../../scenes/relativity/framing';
import { orbitPixelRatio } from '../../scenes/render-budget';

// The baseline horizon is a historical comparison, not part of the selected
// relativistic path. Keep its material and shader payload out of the initial
// preview download until that branch is actually mounted.
const EventHorizon = lazy(async () => {
  const module = await import('../../scenes/EventHorizon');
  return { default: module.EventHorizon };
});

declare global {
  interface Window {
    __orbitScene?: {
      blend: number;
      entrance: number;
      formation: number;
      direction: number;
      frames: number;
      calls: number;
      geometries: number;
      study: MotionStudy;
      horizonRenderer: 'baseline' | 'relativistic';
      textures: number;
      quality: number;
      pixelRatio: number;
      time: number;
      bufferWidth: number;
      bufferHeight: number;
    };
  }
}
export interface OrbitCanvasProps {
  blend: MotionValue<number>;
  entrance: MotionValue<number>;
  direction?: MotionValue<number>;
  study: MotionStudy;
  paused: boolean;
  capture: boolean;
  onReady(): void;
  onPrepared?(): void;
  onQuality?(quality: number): void;
  prepareHorizon?: boolean;
  onSoftware?(): void;
  onFailure(reason?: string): void;
  horizonRenderer: 'baseline' | 'relativistic';
  diskStyle: DiskStyle;
  inclination: number;
  bloom: number;
  horizonTreatment: HorizonTreatment;
  horizonDiagnostic: HorizonDiagnostic;
  transitionDiagnostic?: 'beauty' | 'material' | 'waves';
  ruptureStyle?: RuptureStyle;
  glitchDiagnostic?: GlitchDiagnostic;
  waveMode?: 'planar' | 'spatial';
  streamingWaves?: boolean;
  accretionStyle?: AccretionStyle;
  cubeArrival?: CubeArrivalStyle;
  sceneTime?: MotionValue<number>;
}
function OpticalPostprocessing({
  presence,
  amount,
}: {
  presence: { get(): number };
  amount: number;
}) {
  const effect = useRef<BloomEffect>(null);
  const toneMapping = useRef<ToneMappingEffect>(null);
  const pass = useRef<EffectPass>(null);
  const warmed = useRef(false);
  useFrame(() => {
    if (effect.current) effect.current.intensity = amount * presence.get();
    if (toneMapping.current)
      toneMapping.current.blendMode.opacity.value = presence.get();
    if (pass.current) {
      // Prepare this pass once, then skip its blur pyramid when it contributes
      // nothing. Keeping the pass mounted avoids first-transition compilation.
      pass.current.enabled = !warmed.current || presence.get() > 0;
      warmed.current = true;
    }
  }, -1);
  return (
    <EffectComposer multisampling={0} enableNormalPass={false}>
      <EffectGroup ref={pass}>
        <Bloom
          ref={effect}
          intensity={amount}
          luminanceThreshold={1.2}
          luminanceSmoothing={0.2}
          mipmapBlur
          levels={4}
          radius={0.5}
          resolutionScale={0.5}
        />
        <ToneMapping
          ref={toneMapping}
          mode={ToneMappingMode.ACES_FILMIC}
          blendFunction={BlendFunction.NORMAL}
        />
      </EffectGroup>
    </EffectComposer>
  );
}
function RenderBudget({
  quality,
  capture,
}: {
  quality: number;
  capture: boolean;
}) {
  const { size, setDpr, viewport } = useThree();
  useLayoutEffect(() => {
    const ratio = capture
      ? 1.2
      : orbitPixelRatio(
          size.width,
          size.height,
          window.devicePixelRatio,
          quality,
        );
    // Canvas configuration can reset DPR after initialization or a parent update.
    // Observe the actual renderer value as well as the requested quality.
    if (viewport.dpr !== ratio) setDpr(ratio);
  }, [size.width, size.height, viewport.dpr, quality, capture, setDpr]);
  return null;
}
function World(props: OrbitCanvasProps & { quality: number }) {
  const { camera, invalidate, gl } = useThree();
  const { blend, entrance, onFailure } = props;
  const [initialTime] = useState(() => {
    if (!props.capture) return 12;
    const requested = Number(
      new URLSearchParams(window.location.search).get('sceneTime') ?? '12',
    );
    return Number.isFinite(requested)
      ? MathUtils.clamp(requested, 0, 3600)
      : 12;
  });
  const time = useRef(initialTime);
  const frames = useRef(0);
  const metrics = useRef<NonNullable<Window['__orbitScene']> | null>(null);
  const [opticsReady, setOpticsReady] = useState(false);
  const [baselineReady, setBaselineReady] = useState(false);
  const announced = useRef(false);
  const onOpticsReady = useCallback(() => setOpticsReady(true), []);
  const onBaselineReady = useCallback(() => setBaselineReady(true), []);
  const onPrepared = props.onPrepared;
  useEffect(() => {
    if (opticsReady || baselineReady) onPrepared?.();
  }, [opticsReady, baselineReady, onPrepared]);
  const choreography =
    props.horizonRenderer === 'relativistic' &&
    props.horizonTreatment === 'limb';
  const expressive = choreography && props.study === 'collapse';
  const accretionStyle = props.accretionStyle ?? 'orbit';
  const depositing = expressive && accretionStyle !== 'legacy';
  const ruptureStyle = props.ruptureStyle ?? 'glitch';
  const mirror = ruptureStyle !== 'material';
  const glitch = ruptureStyle === 'glitch';
  const spatialWaves = props.waveMode !== 'planar';
  const radiationMap = useRef<Texture | null>(null);
  const direction = props.direction;
  const formation = useMemo(
    () => ({
      get: () =>
        Math.min(
          entrance.get(),
          expressive
            ? direction?.get() === -1
              ? 1
              : depositing
                ? blend.get()
                : MathUtils.smoothstep(blend.get(), 0.44, 0.94)
            : MathUtils.smoothstep(blend.get(), 0.3, 0.98),
        ),
    }),
    [entrance, blend, expressive, direction, depositing],
  );
  const reveal = useMemo(
    () => ({
      get: () =>
        (expressive && direction?.get() === -1
          ? 1 -
            MathUtils.smoothstep(
              1 - props.blend.get(),
              mirror ? 0.92 : 0.3,
              mirror ? 1 : 0.66,
            )
          : MathUtils.smoothstep(
              props.blend.get(),
              depositing ? 0.18 : expressive ? 0.4 : choreography ? 0.3 : 0.5,
              depositing ? 0.4 : expressive ? 0.68 : choreography ? 0.62 : 0.88,
            )) *
        (choreography
          ? MathUtils.smoothstep(props.entrance.get(), 0, 0.16)
          : props.entrance.get()),
    }),
    [
      props.blend,
      props.entrance,
      choreography,
      expressive,
      direction,
      mirror,
      depositing,
    ],
  );
  useEffect(() => {
    const a = blend.on('change', () => invalidate());
    const b = entrance.on('change', () => invalidate());
    const c = direction?.on('change', () => invalidate());
    const d = props.sceneTime?.on('change', () => invalidate());
    const lost = (event: Event) => {
      event.preventDefault();
      onFailure('context-lost');
    };
    gl.domElement.addEventListener('webglcontextlost', lost);
    return () => {
      a();
      b();
      c?.();
      d?.();
      gl.domElement.removeEventListener('webglcontextlost', lost);
    };
  }, [blend, entrance, direction, props.sceneTime, onFailure, invalidate, gl]);
  useFrame((_, delta) => {
    if (props.sceneTime) time.current = props.sceneTime.get();
    else if (!props.paused && !props.capture)
      time.current += Math.min(delta, 0.05);
    const mix = props.blend.get();
    // The master material clock is linear; the camera arrives with zero velocity.
    const pose = depositing ? MathUtils.smootherstep(mix, 0, 1) : mix;
    camera.position.set(
      Math.sin(time.current * 0.08) * 0.7,
      1.2 + pose * 0.2,
      18 + pose * 4,
    );
    camera.lookAt(0, pose * 1.4, -25 - pose * 13);
    camera.updateMatrixWorld();
    frames.current++;
    // A cube-first visit can present its own scene before the horizon's
    // optical tables and reverse-transition material finish preparing. The
    // destination remains gated by onPrepared in the parent until it is safe
    // to start a horizon transition.
    const initialCubes = props.blend.get() < 0.5;
    const ready =
      props.horizonRenderer === 'baseline'
        ? baselineReady
        : initialCubes || opticsReady;
    if (!announced.current && ready) {
      announced.current = true;
      props.onReady();
    }
    // Keep the diagnostics object stable. Replacing it on every submitted frame
    // creates avoidable garbage without changing the observable values.
    const current =
      metrics.current ??
      (metrics.current = {
        blend: 0,
        entrance: 0,
        formation: 0,
        direction: 1,
        frames: 0,
        calls: 0,
        geometries: 0,
        study: props.study,
        horizonRenderer: props.horizonRenderer,
        textures: 0,
        quality: props.quality,
        pixelRatio: 1,
        time: 0,
        bufferWidth: 0,
        bufferHeight: 0,
      });
    current.blend = mix;
    current.entrance = entrance.get();
    current.formation = formation.get();
    current.direction = direction?.get() ?? 1;
    current.frames = frames.current;
    current.calls = gl.info.render.calls;
    current.geometries = gl.info.memory.geometries;
    current.study = props.study;
    current.horizonRenderer = props.horizonRenderer;
    current.textures = gl.info.memory.textures;
    current.quality = props.quality;
    current.pixelRatio = gl.getPixelRatio();
    current.time = time.current;
    current.bufferWidth = gl.domElement.width;
    current.bufferHeight = gl.domElement.height;
    window.__orbitScene = current;
    gl.info.reset();
  }, -3);
  return (
    <>
      {props.horizonRenderer === 'baseline' ? (
        <Suspense fallback={null}>
          <EventHorizon
            settings={scenes}
            time={time}
            presence={reveal}
            onReady={onBaselineReady}
          />
        </Suspense>
      ) : (
        <RelativisticHorizon
          settings={scenes}
          time={time}
          presence={reveal}
          formation={choreography ? formation : undefined}
          transition={expressive ? blend : undefined}
          direction={direction}
          ruptureStyle={ruptureStyle}
          accretionStyle={accretionStyle}
          glitchDiagnostic={props.glitchDiagnostic}
          waveOnly={props.transitionDiagnostic === 'waves'}
          spatialWaves={spatialWaves}
          radiationMap={radiationMap}
          diskStyle={props.diskStyle}
          inclination={props.inclination}
          treatment={props.horizonTreatment}
          diagnostic={props.horizonDiagnostic}
          onReady={onOpticsReady}
          onFailure={onFailure}
          prepare={props.prepareHorizon !== false}
        />
      )}
      {(!props.transitionDiagnostic ||
        props.transitionDiagnostic === 'beauty') && (
        <CubeCloud
          settings={scenes}
          time={time}
          quality={props.quality}
          collapse={props.blend}
          presence={props.entrance}
          swirl={motionStudies[props.study].swirl}
          linearOutput={props.horizonRenderer === 'relativistic'}
          horizonTreatment={props.horizonTreatment}
          choreography={choreography}
          accretionStyle={accretionStyle}
          cubeArrival={props.cubeArrival}
          expressive={expressive}
          mirrorRupture={mirror}
          glitchRupture={glitch}
          direction={direction}
          inclination={props.inclination}
        />
      )}
      {expressive &&
        !depositing &&
        props.transitionDiagnostic !== 'material' && (
          <SceneImpulse
            progress={blend}
            direction={direction}
            time={time}
            mirror={mirror}
            spatialWaves={spatialWaves || glitch}
          />
        )}
      {expressive && ruptureStyle === 'mirror' && spatialWaves && (
        <RadiationField
          progress={blend}
          direction={direction}
          time={time}
          streaming={props.streamingWaves !== false}
          map={radiationMap}
          showEmission={props.transitionDiagnostic !== 'material'}
        />
      )}
      {props.horizonRenderer === 'relativistic' && (
        <OpticalPostprocessing
          presence={reveal}
          amount={props.horizonDiagnostic === 'beauty' ? props.bloom : 0}
        />
      )}
    </>
  );
}
function OrbitCanvas(props: OrbitCanvasProps) {
  const [quality, setQuality] = useState(1);
  const onQuality = props.onQuality;
  useEffect(() => {
    onQuality?.(quality);
  }, [onQuality, quality]);
  const lowerQuality = useCallback(
    () => setQuality((current) => Math.max(0.45, current - 0.25)),
    [],
  );
  return (
    <Canvas
      camera={{ fov: 62, near: 0.1, far: 160, position: [0, 1.2, 18] }}
      dpr={props.capture ? 1.2 : 1}
      frameloop={props.paused || props.capture ? 'demand' : 'always'}
      gl={{
        // Keep the default framebuffer antialiased: disabling it leaves the
        // first demand frame blank in the tested Linux WebKit compositor.
        // Postprocessing targets still use multisampling={0}.
        antialias: true,
        alpha: false,
        powerPreference: 'high-performance',
      }}
      onCreated={({ gl }) => {
        gl.info.autoReset = false;
        if (
          props.horizonRenderer === 'relativistic' &&
          !gl.extensions.has('EXT_color_buffer_float')
        ) {
          props.onFailure('float-buffer');
          return;
        }
        const context = gl.getContext();
        const debug = context.getExtension('WEBGL_debug_renderer_info');
        const rendererName = String(
          debug
            ? context.getParameter(debug.UNMASKED_RENDERER_WEBGL)
            : context.getParameter(context.RENDERER),
        );
        if (
          /swiftshader|llvmpipe|software|warp|basic render driver|microsoft basic/i.test(
            rendererName,
          )
        )
          props.onSoftware?.();
        gl.debug.onShaderError = (context, _program, vertex, fragment) => {
          console.error(
            'Orbit shader failed',
            context.getShaderInfoLog(vertex),
            context.getShaderInfoLog(fragment),
          );
          props.onFailure('shader');
        };
        gl.outputColorSpace = SRGBColorSpace;
        gl.toneMapping = ACESFilmicToneMapping;
        gl.toneMappingExposure = 0.82;
        gl.setClearColor('#030a12');
      }}
      fallback={<span>Still view</span>}
    >
      <RenderBudget quality={quality} capture={props.capture} />
      {!props.capture && !props.paused && (
        <PerformanceMonitor
          bounds={() => [45, 58]}
          ms={200}
          iterations={6}
          onDecline={lowerQuality}
        />
      )}
      <World {...props} quality={quality} />
    </Canvas>
  );
}

// Song progress updates must not invalidate an otherwise idle scene canvas.
export default memo(OrbitCanvas);
