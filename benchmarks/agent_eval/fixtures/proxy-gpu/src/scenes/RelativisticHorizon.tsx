import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  DoubleSide,
  ShaderMaterial,
  Vector2,
  Vector3,
  type Mesh,
  type Texture,
} from 'three';
import type { SceneProps, SceneSignal } from './CubeCloud';
import { loadOpticalTextures, type OpticalTextures } from './relativity/tables';
import { TABLE_SIZES } from './relativity/optics';
import {
  HORIZON_CENTER,
  HORIZON_VIEW_HEIGHT,
  horizonViewHeight,
  type HorizonTreatment,
} from './relativity/framing';
import definitions from './relativity/bruneton-definitions.glsl?raw';
import functions from './relativity/bruneton-functions.glsl?raw';
import ribbonGeometry from './materials/ribbonGeometry.glsl?raw';
import mirrorVertex from './materials/mirrorVertex.glsl?raw';
import mirrorWaves from './materials/mirrorWaves.glsl?raw';
import { accretionModes, type AccretionStyle } from './accretion';
import accretionGeometry from './materials/accretion.glsl?raw';
import { GlitchSurface } from './GlitchSurface';
import type { GlitchDiagnostic } from './glitch';
import { createMirrorGeometry } from './mirrorGeometry';
import fragment from './materials/relativisticHorizon.glsl?raw';

export type DiskStyle = 'silk' | 'turbulent';
export type HorizonDiagnostic = 'beauty' | 'coordinates' | 'emission';
export type RuptureStyle = 'material' | 'mirror' | 'glitch';
const opticalFunctions = `
${definitions}
#define IN(x) x
#define OUT(x) out x
#define RAY_DEFLECTION_TEXTURE_WIDTH ${TABLE_SIZES.deflection[0]}
#define RAY_DEFLECTION_TEXTURE_HEIGHT ${TABLE_SIZES.deflection[1]}
#define RAY_INVERSE_RADIUS_TEXTURE_WIDTH ${TABLE_SIZES.inverseRadius[0]}
#define RAY_INVERSE_RADIUS_TEXTURE_HEIGHT ${TABLE_SIZES.inverseRadius[1]}
${functions.replaceAll('texture(', 'opticalSample(')}
`;

export function RelativisticHorizon({
  settings,
  time,
  presence,
  formation,
  transition,
  direction,
  ruptureStyle = 'material',
  glitchDiagnostic = 'beauty',
  waveOnly = false,
  spatialWaves = false,
  radiationMap,
  accretionStyle = 'legacy',
  diskStyle,
  inclination,
  treatment,
  diagnostic,
  onReady,
  onFailure,
  prepare = true,
}: SceneProps & {
  presence: SceneSignal;
  formation?: SceneSignal;
  transition?: SceneSignal;
  direction?: SceneSignal;
  ruptureStyle?: RuptureStyle;
  accretionStyle?: AccretionStyle;
  glitchDiagnostic?: GlitchDiagnostic;
  waveOnly?: boolean;
  spatialWaves?: boolean;
  radiationMap?: RefObject<Texture | null>;
  diskStyle: DiskStyle;
  inclination: number;
  treatment: HorizonTreatment;
  diagnostic: HorizonDiagnostic;
  onReady(): void;
  onFailure(reason?: string): void;
  prepare?: boolean;
}) {
  const { size, camera, invalidate, gl } = useThree();
  const [textures, setTextures] = useState<OpticalTextures | null>(null);
  const ready = useRef(false);
  const center = useMemo(() => new Vector3(), []);
  const mesh = useRef<Mesh>(null);
  const geometry = useMemo(
    () => createMirrorGeometry(settings.seed, size.width / size.height),
    [settings.seed, size.width, size.height],
  );
  useEffect(() => () => geometry.dispose(), [geometry]);
  const material = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: mirrorVertex,
        fragmentShader: fragment
          .replace('/* OPTICAL_FUNCTIONS */', opticalFunctions)
          .replace('/* RIBBON_GEOMETRY */', ribbonGeometry)
          .replace('/* ACCRETION_GEOMETRY */', accretionGeometry)
          .replace('/* MIRROR_WAVES */', mirrorWaves),
        uniforms: {
          uDeflection: { value: null },
          uInverseRadius: { value: null },
          uTime: { value: 0 },
          uAspect: { value: 1 },
          uViewHeight: { value: HORIZON_VIEW_HEIGHT },
          uPresence: { value: 0 },
          uFormation: { value: 1 },
          uAccretionStyle: { value: 0 },
          uChoreography: { value: false },
          uTransition: { value: 1 },
          uDirection: { value: 1 },
          uExpressive: { value: false },
          uMirrorRupture: { value: false },
          uFractureOverride: { value: -1 },
          uGlitchSource: { value: false },
          uWaveOnly: { value: false },
          uSpatialWaves: { value: false },
          uRadiationMap: { value: null },
          uResolution: { value: new Vector2() },
          uInclination: { value: 0.2 },
          uTurbulence: { value: 1 },
          uLimb: { value: 0 },
          uFlowView: { value: 0 },
          uSeed: { value: settings.seed },
          uCenter: { value: new Vector2(0.5, 0.5) },
        },
        transparent: true,
        depthWrite: false,
        depthTest: false,
        side: DoubleSide,
        forceSinglePass: true,
      }),
    [settings.seed],
  );
  useEffect(() => {
    // Cube-first visits defer the 2.1 MB optical tables and the reverse-material
    // compilation until the cube arrival has finished, so preparation cannot
    // stall the authored opening.
    if (!prepare) return;
    const controller = new AbortController();
    let resource: OpticalTextures | null = null;
    loadOpticalTextures(controller.signal)
      .then((loaded) => {
        resource = loaded;
        if (controller.signal.aborted) {
          loaded.dispose();
          return;
        }
        material.uniforms.uDeflection!.value = loaded.deflection;
        material.uniforms.uInverseRadius!.value = loaded.inverseRadius;
        setTextures(loaded);
        invalidate();
      })
      .catch(() => {
        if (!controller.signal.aborted) onFailure('optics');
      });
    return () => {
      controller.abort();
      resource?.dispose();
    };
  }, [material, onFailure, invalidate, prepare]);
  useEffect(() => () => material.dispose(), [material]);
  useFrame(() => {
    material.uniforms.uTime!.value = time.current;
    material.uniforms.uAccretionStyle!.value = accretionModes[accretionStyle];
    material.uniforms.uPresence!.value = presence.get();
    material.uniforms.uFormation!.value = formation?.get() ?? 1;
    material.uniforms.uChoreography!.value = Boolean(formation);
    material.uniforms.uTransition!.value = transition?.get() ?? 1;
    material.uniforms.uDirection!.value = direction?.get() ?? 1;
    material.uniforms.uExpressive!.value = Boolean(transition);
    material.uniforms.uMirrorRupture!.value = ruptureStyle === 'mirror';
    material.uniforms.uGlitchSource!.value = ruptureStyle === 'glitch';
    material.uniforms.uWaveOnly!.value = waveOnly;
    material.uniforms.uSpatialWaves!.value = spatialWaves;
    material.uniforms.uRadiationMap!.value = radiationMap?.current ?? null;
    gl.getDrawingBufferSize(material.uniforms.uResolution!.value);
    if (mesh.current) {
      mesh.current.visible = presence.get() >= 0.001 || !ready.current;
      mesh.current.renderOrder =
        transition && ruptureStyle === 'mirror' && direction?.get() === -1
          ? 10
          : -100;
    }
    material.uniforms.uAspect!.value = size.width / size.height;
    material.uniforms.uViewHeight!.value = horizonViewHeight(
      size.width,
      size.height,
      treatment,
    );
    material.uniforms.uInclination!.value = (inclination * Math.PI) / 180;
    material.uniforms.uTurbulence!.value = diskStyle === 'silk' ? 0.12 : 1;
    material.uniforms.uLimb!.value = treatment === 'limb' ? 1 : 0;
    material.uniforms.uFlowView!.value =
      diagnostic === 'coordinates' ? 1 : diagnostic === 'emission' ? 2 : 0;
    center.set(...HORIZON_CENTER).project(camera);
    material.uniforms.uCenter!.value.set(
      center.x * 0.5 + 0.5,
      center.y * 0.5 + 0.5,
    );
  }, -2);
  const announceReady = () => {
    if (!ready.current) {
      ready.current = true;
      onReady();
    }
  };
  if (textures && ruptureStyle === 'glitch')
    return (
      <GlitchSurface
        geometry={geometry}
        source={material}
        diagnostic={glitchDiagnostic}
        onReady={announceReady}
      />
    );
  return (
    textures && (
      <mesh
        ref={mesh}
        geometry={geometry}
        material={material}
        frustumCulled={false}
        renderOrder={-100}
        onAfterRender={announceReady}
      />
    )
  );
}
