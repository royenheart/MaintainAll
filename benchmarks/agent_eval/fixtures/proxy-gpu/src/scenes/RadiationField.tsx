import { useEffect, useMemo, useRef, type RefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useFBO } from '@react-three/drei/core/Fbo';
import {
  AdditiveBlending,
  Color,
  DoubleSide,
  Mesh,
  Scene,
  ShaderMaterial,
  type Texture,
  type PerspectiveCamera,
} from 'three';
import type { SceneSignal } from './CubeCloud';
import { HORIZON_CENTER, horizonViewHeight } from './relativity/framing';
import { createRadiationGeometry, updateRadiationGeometry } from './radiation';
import vertexShader from './materials/radiationVertex.glsl?raw';
import fragmentShader from './materials/radiationFragment.glsl?raw';

export function RadiationField({
  progress,
  direction,
  time,
  map,
  showEmission = true,
  worldScale,
  streaming = true,
}: {
  progress: SceneSignal;
  direction?: SceneSignal;
  time: { current: number };
  map?: RefObject<Texture | null>;
  showEmission?: boolean;
  worldScale?: number;
  streaming?: boolean;
}) {
  const { size, gl, camera } = useThree();
  const target = useFBO(Math.ceil(size.width / 2), Math.ceil(size.height / 2), {
    depthBuffer: false,
    stencilBuffer: false,
  });
  const geometry = useMemo(createRadiationGeometry, []);
  const uniforms = useMemo(
    () => ({
      uWorldScale: { value: 5 },
      uAspect: { value: 1 },
      uStreaming: { value: 1 },
      uTime: { value: 12 },
    }),
    [],
  );
  const materials = useMemo(
    () =>
      [0, 1].map(
        (mode) =>
          new ShaderMaterial({
            vertexShader,
            fragmentShader,
            uniforms,
            defines: { DISTORTION: mode },
            transparent: true,
            blending: AdditiveBlending,
            depthTest: false,
            depthWrite: false,
            side: DoubleSide,
            forceSinglePass: true,
          }),
      ),
    [uniforms],
  );
  const offscreen = useMemo(() => {
    const scene = new Scene();
    const mesh = new Mesh(geometry, materials[1]);
    mesh.frustumCulled = false;
    scene.add(mesh);
    return { scene, mesh };
  }, [geometry, materials]);
  const visible = useRef<Mesh>(null);
  const initialized = useRef(false);
  const targetSize = useRef('');
  const wasActive = useRef(false);
  const clearColor = useMemo(() => new Color(), []);
  useEffect(
    () => () => {
      geometry.dispose();
      materials.forEach((material) => material.dispose());
      offscreen.scene.clear();
    },
    [geometry, materials, offscreen],
  );
  useFrame(() => {
    const dimensions = `${target.width}x${target.height}`;
    if (targetSize.current !== dimensions) {
      targetSize.current = dimensions;
      initialized.current = false;
    }
    const q = direction?.get() === -1 ? 1 - progress.get() : 0;
    const active = q > 0 && q < 1;
    const scale =
      worldScale ??
      ((60 *
        2 *
        Math.tan(((camera as PerspectiveCamera).fov * Math.PI) / 360)) /
        horizonViewHeight(size.width, size.height, 'limb')) *
        0.5;
    uniforms.uStreaming.value = streaming ? 1 : 0;
    uniforms.uTime.value = time.current;
    uniforms.uWorldScale.value = scale;
    uniforms.uAspect.value = size.width / size.height;
    if (active || wasActive.current || !initialized.current)
      updateRadiationGeometry(geometry, q, time.current, streaming);
    offscreen.mesh.position.set(...HORIZON_CENTER);
    offscreen.mesh.scale.setScalar(scale);
    if (visible.current) {
      visible.current.visible = active && showEmission;
      visible.current.scale.setScalar(scale);
    }
    if (map) map.current = target.texture;
    // The library-owned target is a vector displacement field, not a scene copy.
    // Render the same world curves with wider support before evaluating the source.
    if (!initialized.current || active || wasActive.current) {
      const previous = gl.getRenderTarget();
      const alpha = gl.getClearAlpha();
      gl.getClearColor(clearColor);
      const autoClear = gl.autoClear;
      gl.autoClear = false;
      gl.setRenderTarget(target);
      gl.setClearColor(0x000000, 0);
      gl.clear();
      gl.render(offscreen.scene, camera);
      gl.setRenderTarget(previous);
      gl.setClearColor(clearColor, alpha);
      gl.autoClear = autoClear;
      initialized.current = true;
    }
    wasActive.current = active;
  }, -2.5);
  return (
    <mesh
      ref={visible}
      position={[...HORIZON_CENTER]}
      geometry={geometry}
      material={materials[0]}
      renderOrder={100}
      frustumCulled={false}
      dispose={null}
    />
  );
}
