import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  MathUtils,
  Vector3,
  type ShaderMaterial,
  type PerspectiveCamera,
  type Group,
  type Mesh,
} from 'three';
import {
  HORIZON_CENTER,
  horizonCaptureRadius,
  horizonViewHeight,
  type HorizonTreatment,
} from './relativity/framing';
import {
  accretionModes,
  type AccretionStyle,
  type CubeArrivalStyle,
} from './accretion';
import accretionGeometry from './materials/accretion.glsl?raw';
import { glitchFractureProgress } from './glitch';
import { createCubeGeometry } from './cubeGeometry';
import ribbonGeometry from './materials/ribbonGeometry.glsl?raw';
import vertexSource from './materials/gpuCubeVertexShader.glsl?raw';
import fragmentShader from './materials/gpuCubeFragmentShader.glsl?raw';
import atmosphereVertex from './materials/gpuAtmosphereVertexShader.glsl?raw';
import atmosphereFragment from './materials/gpuAtmosphereFragmentShader.glsl?raw';
import type { SceneSettings } from '../lib/content/schema';

const vertexShader = vertexSource
  .replace('/* RIBBON_GEOMETRY */', ribbonGeometry)
  .replace('/* ACCRETION_GEOMETRY */', accretionGeometry);

export interface SceneProps {
  settings: SceneSettings;
  time: { current: number };
}
export interface SceneSignal {
  get(): number;
}
export function CubeCloud({
  settings,
  time,
  quality,
  collapse,
  presence,
  swirl = 0,
  linearOutput = false,
  horizonTreatment = 'optical',
  choreography = false,
  expressive = false,
  mirrorRupture = false,
  glitchRupture = false,
  direction,
  inclination = 12,
  accretionStyle = 'legacy',
  cubeArrival = 'gravity',
}: SceneProps & {
  quality: number;
  collapse?: SceneSignal;
  presence?: SceneSignal;
  swirl?: number;
  linearOutput?: boolean;
  horizonTreatment?: HorizonTreatment;
  choreography?: boolean;
  expressive?: boolean;
  mirrorRupture?: boolean;
  glitchRupture?: boolean;
  direction?: SceneSignal;
  inclination?: number;
  accretionStyle?: AccretionStyle;
  cubeArrival?: CubeArrivalStyle;
}) {
  const size = useThree((state) => state.size);
  const camera = useThree((state) => state.camera);
  const centerView = useMemo(() => new Vector3(), []);
  const group = useRef<Group>(null);
  const background = useRef<Mesh>(null);
  // Keep particle identities stable while adaptive DPR changes during a morph.
  const count = Math.round(settings.cubeCount * (choreography ? 1 : quality));
  const geometry = useMemo(
    () => createCubeGeometry(count, settings.seed),
    [count, settings.seed],
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  const cubes = useRef<ShaderMaterial>(null);
  const backdrop = useRef<ShaderMaterial>(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uAccretionStyle: { value: 0 },
      uGravityArrival: { value: true },
      uFallTop: { value: 23 },
      uFallBottom: { value: -17 },
      uVerticalDensityPower: { value: 1.85 },
      uPileHoldStart: { value: 0.72 },
      uPileFadeStart: { value: 0.94 },
      uLightContrast: { value: 1.34 },
      uCollapse: { value: 0 },
      uPresence: { value: 1 },
      uChoreography: { value: false },
      uExpressive: { value: false },
      uMirrorRupture: { value: false },
      uFractureOverride: { value: -1 },
      uDirection: { value: 1 },
      uInclination: { value: 0.2 },
      uWorldPerScreen: { value: 1 },
      uSwirl: { value: 0 },
      uLinearOutput: { value: false },
      uHorizonRadius: { value: 12 },
      uHorizonCenter: { value: new Vector3(...HORIZON_CENTER) },
    }),
    [],
  );
  const atmosphere = useMemo(
    () => ({
      uTime: { value: 0 },
      uAspect: { value: 1 },
      uPresence: { value: 1 },
      uLinearOutput: { value: false },
    }),
    [],
  );
  useFrame(() => {
    const blend = collapse?.get() ?? 0;
    const entry = presence?.get() ?? 1;
    if (group.current) group.current.visible = blend < 1;
    if (cubes.current) {
      cubes.current.uniforms.uTime!.value = time.current;
      cubes.current.uniforms.uAccretionStyle!.value =
        accretionModes[accretionStyle];
      cubes.current.uniforms.uGravityArrival!.value = cubeArrival === 'gravity';
      cubes.current.uniforms.uCollapse!.value = blend;
      cubes.current.uniforms.uPresence!.value = entry;
      cubes.current.uniforms.uChoreography!.value = choreography;
      cubes.current.uniforms.uExpressive!.value = expressive;
      cubes.current.uniforms.uMirrorRupture!.value = mirrorRupture;
      cubes.current.uniforms.uFractureOverride!.value = glitchRupture
        ? glitchFractureProgress(1 - blend)
        : -1;
      cubes.current.uniforms.uDirection!.value = direction?.get() ?? 1;
      cubes.current.uniforms.uInclination!.value =
        (inclination * Math.PI) / 180;
      centerView.set(...HORIZON_CENTER).applyMatrix4(camera.matrixWorldInverse);
      cubes.current.uniforms.uWorldPerScreen!.value =
        (2 *
          -centerView.z *
          Math.tan(
            (((camera as PerspectiveCamera).fov ?? 62) * Math.PI) / 360,
          )) /
        horizonViewHeight(size.width, size.height, horizonTreatment);
      cubes.current.uniforms.uSwirl!.value = swirl;
      cubes.current.uniforms.uLinearOutput!.value = linearOutput;
      cubes.current.uniforms.uHorizonRadius!.value = horizonCaptureRadius(
        size.width,
        size.height,
        camera.position.z - HORIZON_CENTER[2],
        (camera as PerspectiveCamera).fov ?? 62,
        horizonTreatment,
      );
    }
    if (backdrop.current) {
      backdrop.current.uniforms.uTime!.value = time.current;
      backdrop.current.uniforms.uAspect!.value = size.width / size.height;
      backdrop.current.uniforms.uLinearOutput!.value = linearOutput;
      backdrop.current.uniforms.uPresence!.value =
        entry *
        (1 -
          MathUtils.smoothstep(
            blend,
            expressive && direction?.get() !== -1
              ? 0.08
              : choreography
                ? 0.14
                : 0.06,
            expressive && direction?.get() !== -1
              ? 0.64
              : choreography
                ? 0.7
                : 0.62,
          ));
      if (background.current)
        background.current.visible =
          backdrop.current.uniforms.uPresence!.value > 0;
    }
  });
  return (
    <group ref={group}>
      <mesh ref={background} position={[0, 0, -94]}>
        <planeGeometry args={[320, 190]} />
        <shaderMaterial
          ref={backdrop}
          uniforms={atmosphere}
          vertexShader={atmosphereVertex}
          fragmentShader={atmosphereFragment}
          depthWrite={false}
          transparent
        />
      </mesh>
      <mesh geometry={geometry} frustumCulled={false}>
        <shaderMaterial
          ref={cubes}
          uniforms={uniforms}
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          transparent
          depthWrite
        />
      </mesh>
    </group>
  );
}
