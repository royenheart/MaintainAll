import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import {
  AdditiveBlending,
  type Group,
  type Points,
  type PointsMaterial,
} from 'three';
import {
  eventHorizonBackdropMaterial,
  eventHorizonGlowMaterial,
  eventHorizonCoreMaterial,
  eventHorizonDiskMaterial,
} from './materials/horizon';
import { seededRandom } from './random';
import type { SceneProps, SceneSignal } from './CubeCloud';

export function EventHorizon({
  settings,
  time,
  presence,
  onReady,
}: SceneProps & { presence?: SceneSignal; onReady?(): void }) {
  const { width, height } = useThree((state) => state.size);
  const aspect = width / height;
  const wide = Math.max(1, aspect / 1.5);
  const tall = Math.max(1, 1.5 / aspect);
  const scale = (aspect < 0.75 ? 0.94 : 1) * (aspect > 1.8 ? 0.96 : 1);
  const group = useRef<Group>(null);
  const announced = useRef(false);
  const stars = useRef<Points>(null);
  const starMaterial = useRef<PointsMaterial>(null);
  const materials = useMemo(
    () => ({
      backdrop: eventHorizonBackdropMaterial(),
      glow: eventHorizonGlowMaterial({
        opacity: 0.94,
        intensity: 1.18,
        haloSpread: 1.08,
      }),
      outer: eventHorizonGlowMaterial({
        opacity: 0.42,
        intensity: 0.9,
        haloSpread: 1.64,
      }),
      core: eventHorizonCoreMaterial(),
      disk: eventHorizonDiskMaterial(),
    }),
    [],
  );
  useEffect(
    () => () =>
      Object.values(materials).forEach((material) => material.dispose()),
    [materials],
  );
  const positions = useMemo(() => {
    const { range } = seededRandom(settings.seed + 1);
    return Float32Array.from({ length: 600 }, () => range(-30, 30));
  }, [settings.seed]);
  useFrame(() => {
    if (!announced.current) {
      announced.current = true;
      onReady?.();
    }
    const reveal = presence?.get() ?? 1;
    Object.values(materials).forEach((material) => {
      material.uniforms.uTime!.value = time.current;
      material.uniforms.uPresence!.value = reveal;
      if (material.uniforms.uSceneAspectRatio)
        material.uniforms.uSceneAspectRatio.value = aspect;
    });
    if (group.current) {
      group.current.position.x = Math.sin(time.current * 0.08) * 0.18;
      group.current.scale.setScalar(0.18 + reveal * 0.82);
    }
    if (starMaterial.current) starMaterial.current.opacity = 0.72 * reveal;
    if (stars.current) stars.current.rotation.y = time.current * 0.05;
  });
  return (
    <group>
      <mesh
        position={[0, 0, -72]}
        scale={[1.35 * wide, 1.35 * tall, 1]}
        renderOrder={-10}
        material={materials.backdrop}
      >
        <planeGeometry args={[180, 120]} />
      </mesh>
      <group ref={group} position={[0, aspect < 0.75 ? 1.8 : 1, -38]}>
        <mesh
          position={[0, 0.4, -0.1]}
          scale={[1.56 * scale, 1.9 * scale, 1]}
          renderOrder={0}
          material={materials.outer}
        >
          <planeGeometry args={[64, 44]} />
        </mesh>
        <mesh
          position={[0, 0.5, -0.08]}
          scale={[1.42 * scale, 1.72 * scale, 1]}
          renderOrder={1}
          material={materials.glow}
        >
          <planeGeometry args={[64, 44]} />
        </mesh>
        <mesh
          position={[0, 0.5, 0.02]}
          scale={[1.08 * scale, 1.34 * scale, 1]}
          renderOrder={3}
          material={materials.core}
        >
          <planeGeometry args={[62, 42]} />
        </mesh>
        <mesh
          position={[0, -10.6, 0.08]}
          scale={[1.35 * wide, 1.38 * scale, 1]}
          renderOrder={6}
          material={materials.disk}
        >
          <planeGeometry args={[160, 44]} />
        </mesh>
      </group>
      <points ref={stars} position={[0, 5, -30]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <pointsMaterial
          ref={starMaterial}
          color={settings.horizon.paleGold}
          size={0.2}
          transparent
          opacity={0.72}
          blending={AdditiveBlending}
          depthWrite={false}
        />
      </points>
    </group>
  );
}
