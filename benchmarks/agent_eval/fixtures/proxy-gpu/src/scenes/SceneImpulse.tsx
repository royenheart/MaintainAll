import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  AdditiveBlending,
  Vector2,
  Vector3,
  type Mesh,
  type ShaderMaterial,
} from 'three';
import type { SceneSignal } from './CubeCloud';
import { HORIZON_CENTER, horizonViewHeight } from './relativity/framing';
import fragmentShader from './materials/sceneImpulse.glsl?raw';
import mirrorWaves from './materials/mirrorWaves.glsl?raw';

// A transient emissive field shares the existing camera and postprocessing.
// It adds an inward compression front or outward shock, never a second renderer.
export function SceneImpulse({
  progress,
  direction,
  time,
  mirror = false,
  spatialWaves = false,
}: {
  progress: SceneSignal;
  direction?: SceneSignal;
  time: { current: number };
  mirror?: boolean;
  spatialWaves?: boolean;
}) {
  const { camera, size } = useThree();
  const mesh = useRef<Mesh>(null);
  const material = useRef<ShaderMaterial>(null);
  const center = useMemo(() => new Vector3(), []);
  const uniforms = useMemo(
    () => ({
      uProgress: { value: 0 },
      uDirection: { value: 1 },
      uMirror: { value: false },
      uTime: { value: 0 },
      uAspect: { value: 1 },
      uViewHeight: { value: 7.2 },
      uCenter: { value: new Vector2(0.5, 0.5) },
    }),
    [],
  );
  useFrame(() => {
    const p = progress.get();
    if (mesh.current)
      mesh.current.visible =
        p > 0.001 &&
        p < 0.999 &&
        !(mirror && spatialWaves && direction?.get() === -1);
    if (!material.current) return;
    center.set(...HORIZON_CENTER).project(camera);
    const active = material.current.uniforms;
    active.uProgress!.value = p;
    active.uDirection!.value = direction?.get() ?? 1;
    active.uMirror!.value = mirror;
    active.uTime!.value = time.current;
    active.uAspect!.value = size.width / size.height;
    active.uViewHeight!.value = horizonViewHeight(
      size.width,
      size.height,
      'limb',
    );
    active.uCenter!.value.set(center.x * 0.5 + 0.5, center.y * 0.5 + 0.5);
  }, -2);
  return (
    <mesh ref={mesh} renderOrder={100} frustumCulled={false}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader="varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }"
        fragmentShader={fragmentShader.replace(
          '/* MIRROR_WAVES */',
          mirrorWaves,
        )}
        blending={AdditiveBlending}
        transparent
        depthTest={false}
        depthWrite={false}
      />
    </mesh>
  );
}
