import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useFBO } from '@react-three/drei/core/Fbo';
import {
  Color,
  DoubleSide,
  Mesh,
  Scene,
  ShaderMaterial,
  type BufferGeometry,
} from 'three';
import { glitchFractureProgress, type GlitchDiagnostic } from './glitch';
import vertexShader from './materials/mirrorVertex.glsl?raw';
import fragmentShader from './materials/glitchFragment.glsl?raw';

export function GlitchSurface({
  geometry,
  source,
  diagnostic,
  onReady,
}: {
  geometry: BufferGeometry;
  source: ShaderMaterial;
  diagnostic: GlitchDiagnostic;
  onReady(): void;
}) {
  const { gl, camera, size, viewport, invalidate } = useThree();
  const ratio = Math.min(viewport.dpr, 1);
  const target = useFBO(
    Math.ceil(size.width * ratio),
    Math.ceil(size.height * ratio),
    {
      depthBuffer: false,
      stencilBuffer: false,
    },
  );
  const material = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader,
        fragmentShader,
        uniforms: {
          ...source.uniforms,
          uSource: { value: target.texture },
          uMirrorRupture: { value: true },
          uFractureOverride: { value: 0 },
          uDiagnostic: { value: 0 },
        },
        transparent: true,
        depthTest: false,
        depthWrite: false,
        side: DoubleSide,
        forceSinglePass: true,
      }),
    [source, target.texture],
  );
  const offscreen = useMemo(() => {
    const scene = new Scene();
    const surface = new Mesh(geometry, source);
    surface.frustumCulled = false;
    scene.add(surface);
    return scene;
  }, [geometry, source]);
  const mesh = useRef<Mesh>(null);
  const compiled = useRef(false);
  const announced = useRef(false);
  const available = useRef(true);
  const clearColor = useMemo(() => new Color(), []);
  useEffect(() => {
    let alive = true;
    compiled.current = false;
    const preparation = new Scene();
    preparation.add(new Mesh(geometry, material));
    // Compile the alternate presentation material before exposing the controls.
    // Otherwise its first use can stall the beginning of the authored sequence.
    // Match the linear HDR output used by the composer's scene pass.
    const previous = gl.getRenderTarget();
    let compilation: Promise<unknown>;
    try {
      gl.setRenderTarget(target);
      compilation = gl.compileAsync(preparation, camera);
    } finally {
      gl.setRenderTarget(previous);
    }
    compilation
      .then(() => {
        if (!alive) return;
        compiled.current = true;
        invalidate();
      })
      .catch((error) => {
        if (!alive) return;
        available.current = false;
        // F7 is an optional reverse treatment. A driver-specific compile
        // failure must not discard the working horizon foreground.
        console.warn(
          '[orbit] F7 material unavailable; keeping live horizon',
          error,
        );
      });
    return () => {
      alive = false;
      preparation.clear();
    };
  }, [gl, camera, geometry, material, target, invalidate]);
  useEffect(() => () => material.dispose(), [material]);
  useEffect(
    () => () => {
      offscreen.clear();
    },
    [offscreen],
  );
  useFrame(() => {
    if (!mesh.current) return;
    mesh.current.visible =
      Number(source.uniforms.uPresence!.value) >= 0.001 || !announced.current;
    const q = 1 - Number(source.uniforms.uTransition!.value);
    const active =
      available.current &&
      Boolean(source.uniforms.uExpressive!.value) &&
      Number(source.uniforms.uDirection!.value) < 0 &&
      q > 0 &&
      q < 1;
    mesh.current.material = active ? material : source;
    mesh.current.renderOrder = active ? 10 : -100;
    if (!active) return;
    material.uniforms.uFractureOverride!.value =
      diagnostic === 'field' ? 0 : glitchFractureProgress(q);
    material.uniforms.uDiagnostic!.value =
      diagnostic === 'field' ? 1 : diagnostic === 'sharp' ? 2 : 0;
    const previous = gl.getRenderTarget();
    const alpha = gl.getClearAlpha();
    gl.getClearColor(clearColor);
    const autoClear = gl.autoClear;
    // The source is a live HDR scene, redrawn only during this reverse transition.
    // Bloom and tone mapping run once, after the warped, content-bearing panes.
    try {
      gl.autoClear = false;
      gl.setRenderTarget(target);
      gl.setClearColor(0x000000, 0);
      gl.clear();
      gl.render(offscreen, camera);
    } finally {
      gl.setRenderTarget(previous);
      gl.setClearColor(clearColor, alpha);
      gl.autoClear = autoClear;
    }
  }, -1.9);
  return (
    <mesh
      ref={mesh}
      geometry={geometry}
      material={source}
      frustumCulled={false}
      renderOrder={-100}
      onAfterRender={() => {
        // The source is drawable as soon as its first frame is submitted.
        // F7's alternate material may still be compiling; that must not block
        // the initial horizon arrival or turn a live canvas into a fallback.
        if (!announced.current) {
          announced.current = true;
          onReady();
        }
      }}
      dispose={null}
    />
  );
}
