import { useCallback, useEffect, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { PerformanceMonitor } from '@react-three/drei/core/PerformanceMonitor';
import { ACESFilmicToneMapping, SRGBColorSpace } from 'three';
import { CubeCloud } from '../../scenes/CubeCloud';
import { EventHorizon } from '../../scenes/EventHorizon';
import type { SceneId, SceneSettings } from '../../lib/content/schema';

export interface SceneCanvasProps {
  scene: SceneId;
  settings: SceneSettings;
  paused: boolean;
  capture: boolean;
  onReady: () => void;
  onFailure: () => void;
}
declare global {
  interface Window {
    __sceneMetrics?: {
      frames: number;
      calls: number;
      geometries: number;
      textures: number;
      scene: SceneId;
      dpr: number;
      quality: number;
    };
  }
}

function World({
  scene,
  settings,
  paused,
  capture,
  onReady,
  onFailure,
  quality,
}: SceneCanvasProps & { quality: number }) {
  const { gl, invalidate } = useThree();
  const time = useRef(capture ? 12 : 0);
  const frames = useRef(0);
  useEffect(() => {
    invalidate();
  }, [scene, paused, invalidate]);
  useEffect(() => {
    const canvas = gl.domElement;
    const lost = (event: Event) => {
      event.preventDefault();
      onFailure();
    };
    canvas.addEventListener('webglcontextlost', lost);
    return () => canvas.removeEventListener('webglcontextlost', lost);
  }, [gl, onFailure]);
  useFrame(({ camera }) => {
    if (scene === 'cubes') {
      camera.position.set(
        Math.sin(time.current * 0.08) * 0.7,
        1.2 + Math.sin(time.current * 0.11) * 0.18,
        18 + Math.cos(time.current * 0.08) * 0.45,
      );
      camera.lookAt(0, 0, -25);
    } else {
      camera.position.set(
        Math.sin(time.current * 0.05) * 1.4,
        1.4 + Math.sin(time.current * 0.07) * 0.16,
        22 + Math.cos(time.current * 0.05) * 0.7,
      );
      camera.lookAt(0, 1.4, -38);
    }
  }, -2);
  useFrame((_, delta) => {
    if (!paused && !capture) time.current += Math.min(delta, 0.05);
    frames.current += 1;
    if (frames.current === 1) onReady();
    window.__sceneMetrics = {
      frames: frames.current,
      calls: gl.info.render.calls,
      geometries: gl.info.memory.geometries,
      textures: gl.info.memory.textures,
      scene,
      dpr: gl.getPixelRatio(),
      quality,
    };
  }, -3);
  return (
    <>
      {scene === 'cubes' ? (
        <CubeCloud settings={settings} time={time} quality={quality} />
      ) : (
        <EventHorizon settings={settings} time={time} />
      )}
    </>
  );
}

export default function SceneCanvas(props: SceneCanvasProps) {
  const [quality, setQuality] = useState(1);
  const [dpr, setDpr] = useState(1.35);
  const lowerQuality = useCallback(() => {
    setQuality(0.65);
    setDpr(1);
  }, []);
  return (
    <Canvas
      camera={{ fov: 62, near: 0.1, far: 160, position: [0, 1.1, 18] }}
      dpr={dpr}
      frameloop={props.paused || props.capture ? 'demand' : 'always'}
      gl={{ antialias: true, alpha: true, powerPreference: 'default' }}
      onCreated={({ gl }) => {
        gl.outputColorSpace = SRGBColorSpace;
        gl.toneMapping = ACESFilmicToneMapping;
        gl.toneMappingExposure = 0.82;
      }}
      fallback={<span>Graphics unavailable</span>}
    >
      {!props.capture && !props.paused && (
        <PerformanceMonitor
          flipflops={2}
          onDecline={lowerQuality}
          onFallback={lowerQuality}
        />
      )}
      <World {...props} quality={quality} />
    </Canvas>
  );
}
