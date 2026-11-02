import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei/core/OrbitControls';
import { Line } from '@react-three/drei/core/Line';
import {
  animate,
  useMotionValue,
  useMotionValueEvent,
  type MotionValue,
  type AnimationPlaybackControls,
} from 'motion/react';
import { DoubleSide } from 'three';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { RadiationField } from '../../scenes/RadiationField';
import { radiationRays } from '../../scenes/radiation';
import { HORIZON_CENTER } from '../../scenes/relativity/framing';
import { useReducedMotionPreference } from '../../lib/useReducedMotionPreference';
import './formation-study.css';

type View = 'oblique' | 'top' | 'front';
const views = {
  oblique: [85, 65, 90],
  top: [0, 140, -20],
  front: [0, 12, 105],
} as const;

function Space({
  blend,
  view,
  streaming,
  ready,
}: {
  blend: MotionValue<number>;
  view: View;
  streaming: boolean;
  ready(): void;
}) {
  const { camera, invalidate } = useThree();
  const announced = useRef(false);
  const time = useRef(12);
  const direction = useMemo(() => ({ get: () => -1 }), []);
  useEffect(() => invalidate(), [streaming, invalidate]);
  useEffect(() => blend.on('change', invalidate), [blend, invalidate]);
  useEffect(() => {
    camera.position.fromArray(views[view]);
    camera.lookAt(...HORIZON_CENTER);
    invalidate();
  }, [camera, invalidate, view]);
  useFrame(() => {
    if (!announced.current) {
      announced.current = true;
      ready();
    }
  });
  return (
    <>
      <OrbitControls target={[...HORIZON_CENTER]} enableDamping={false} />
      <group position={[...HORIZON_CENTER]}>
        <mesh>
          <sphereGeometry args={[26, 24, 12]} />
          <meshBasicMaterial
            color="#45505f"
            wireframe
            transparent
            opacity={0.22}
          />
        </mesh>
        <gridHelper
          args={[150, 15, '#2b3945', '#18232e']}
          rotation={[Math.PI / 15, 0, 0]}
        />
        {[27.5, 40, 55].map((radius) => (
          <mesh key={radius} rotation={[-Math.PI / 2 + Math.PI / 15, 0, 0]}>
            <ringGeometry args={[radius - 0.08, radius + 0.08, 100]} />
            <meshBasicMaterial
              color="#866840"
              side={DoubleSide}
              transparent
              opacity={0.6}
            />
          </mesh>
        ))}
        {radiationRays.slice(0, 5).map((ray) => (
          <Line
            key={ray.angle}
            points={[
              [0, 0, 0],
              [
                Math.sin(ray.angle) * 65,
                -Math.sin(Math.PI / 15) * Math.cos(ray.angle) * 65,
                Math.cos(Math.PI / 15) * Math.cos(ray.angle) * 65,
              ],
            ]}
            color="#665338"
            lineWidth={0.7}
            transparent
            opacity={0.7}
          />
        ))}
      </group>
      <RadiationField
        progress={blend}
        direction={direction}
        time={time}
        worldScale={5}
        streaming={streaming}
      />
    </>
  );
}
function RadiationStudy() {
  const blend = useMotionValue(0.64);
  const [release, setRelease] = useState(0.36);
  const [view, setView] = useState<View>('oblique');
  const [streaming, setStreaming] = useState(true);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const playback = useRef<AnimationPlaybackControls | null>(null);
  const reduced = useReducedMotionPreference();
  useMotionValueEvent(blend, 'change', (value) => setRelease(1 - value));
  useEffect(() => () => playback.current?.stop(), []);
  const play = () => {
    playback.current?.stop();
    blend.set(1);
    setPlaying(true);
    playback.current = animate(blend, 0, {
      duration: reduced ? 0 : 5.4,
      ease: 'linear',
      onComplete: () => setPlaying(false),
    });
  };
  return (
    <main className="formation-study" data-ready={ready} data-playing={playing}>
      <div
        className="formation-stage"
        role="img"
        aria-label="Three-dimensional radiation geometry"
      >
        <Canvas
          camera={{
            fov: 48,
            near: 0.1,
            far: 600,
            position: [...views.oblique],
          }}
          frameloop="demand"
          dpr={1}
          fallback={<span>Graphics unavailable</span>}
        >
          <color attach="background" args={['#050b12']} />
          <Space
            blend={blend}
            view={view}
            streaming={streaming}
            ready={() => setReady(true)}
          />
        </Canvas>
      </div>
      <section
        className="formation-controls"
        aria-label="Spatial radiation controls"
      >
        <p>
          F6 · world-space wave strands · drag to orbit
          <span>{Math.round(release * 100)}% release</span>
        </p>
        <label>
          Release
          <input
            aria-label="Release progress"
            type="range"
            min="0"
            max="1"
            step="0.001"
            value={release}
            onChange={(event) => {
              playback.current?.stop();
              setPlaying(false);
              blend.set(1 - Number(event.target.value));
            }}
          />
        </label>
        <div className="formation-actions">
          <button onClick={play}>Replay radiation</button>
          <button
            aria-pressed={streaming}
            onClick={() => setStreaming((value) => !value)}
          >
            {streaming ? 'Compare short strands' : 'Show continuous strands'}
          </button>
          {(['oblique', 'top', 'front'] as const).map((pose) => (
            <button
              key={pose}
              onClick={() => setView(pose)}
              aria-pressed={view === pose}
            >
              {pose === 'oblique'
                ? 'Oblique view'
                : pose === 'top'
                  ? 'Top view'
                  : 'Front view'}
            </button>
          ))}
        </div>
        <small>
          The same curves and radial paths used in the scene · guides are
          diagnostic only
        </small>
      </section>
    </main>
  );
}
const meta = {
  title: 'Explorations/Spatial radiation',
  component: RadiationStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
} satisfies Meta<typeof RadiationStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const WorldSpaceFan: Story = {};
