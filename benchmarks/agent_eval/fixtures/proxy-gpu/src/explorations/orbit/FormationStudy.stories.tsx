import { useCallback, useEffect, useRef, useState } from 'react';
import {
  animate,
  useMotionValue,
  useMotionValueEvent,
  type AnimationPlaybackControls,
} from 'motion/react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import type { AccretionStyle, CubeArrivalStyle } from '../../scenes/accretion';
import OrbitCanvas from './OrbitCanvas';
import { formationTiming } from './formation';
import { useReducedMotionPreference } from '../../lib/useReducedMotionPreference';
import './formation-study.css';

type Sequence = 'transition' | 'cubes' | 'horizon';
type Expression = 'continuous' | 'force';
function FormationStudy({
  sequence = 'transition',
  expression = 'continuous',
  materialOnly = false,
  ruptureStyle = 'material',
  waveOnly = false,
  waveMode = 'planar',
  streamingWaves = false,
  glitchDiagnostic = 'beauty',
  accretionStyle = 'legacy',
  cubeArrival = 'gravity',
}: {
  sequence?: Sequence;
  accretionStyle?: AccretionStyle;
  cubeArrival?: CubeArrivalStyle;
  expression?: Expression;
  materialOnly?: boolean;
  ruptureStyle?: 'material' | 'mirror' | 'glitch';
  glitchDiagnostic?: 'beauty' | 'field' | 'sharp';
  waveOnly?: boolean;
  waveMode?: 'planar' | 'spatial';
  streamingWaves?: boolean;
}) {
  const startsAtHorizon =
    sequence === 'horizon' ||
    (sequence === 'transition' &&
      (materialOnly || ruptureStyle !== 'material') &&
      accretionStyle === 'legacy');
  const blend = useMotionValue(startsAtHorizon ? 1 : 0);
  const entrance = useMotionValue(sequence === 'transition' ? 1 : 0);
  const direction = useMotionValue(startsAtHorizon ? -1 : 1);
  const progress = sequence === 'transition' ? blend : entrance;
  const reduced = useReducedMotionPreference();
  const [value, setValue] = useState(
    sequence === 'transition' && startsAtHorizon ? 1 : 0,
  );
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [mounted, setMounted] = useState(true);
  const animation = useRef<AnimationPlaybackControls | null>(null);
  const capture =
    new URLSearchParams(window.location.search).get('capture') === '1';
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback(() => {
    setFailed(true);
    setPlaying(false);
    animation.current?.stop();
  }, []);
  useMotionValueEvent(progress, 'change', setValue);
  useEffect(() => () => animation.current?.stop(), []);
  const stop = () => {
    animation.current?.stop();
    setPlaying(false);
  };
  const play = (target: number) => {
    stop();
    const nextDirection = target === 1 ? 1 : -1;
    if (
      expression === 'force' &&
      sequence === 'transition' &&
      direction.get() !== nextDirection
    )
      progress.set(1 - target);
    direction.set(nextDirection);
    if (Math.abs(progress.get() - target) < 0.001) progress.set(1 - target);
    setPlaying(true);
    animation.current = animate(progress, target, {
      duration: reduced
        ? 0
        : (expression === 'force' && sequence === 'transition'
            ? formationTiming[
                target === 1
                  ? 'collapse'
                  : ruptureStyle === 'glitch'
                    ? 'glitch'
                    : ruptureStyle === 'mirror'
                      ? 'mirror'
                      : 'rupture'
              ]
            : formationTiming[sequence]) * Math.abs(target - progress.get()),
      ease: 'linear',
      onComplete: () => setPlaying(false),
    });
  };
  return (
    <main
      className="formation-study"
      data-sequence={sequence}
      data-ready={ready}
      data-playing={playing}
      data-expression={expression}
    >
      <div
        className="formation-stage"
        role="img"
        aria-label="Scene formation preview"
      >
        {mounted && (
          <OrbitCanvas
            blend={blend}
            entrance={entrance}
            study={expression === 'force' ? 'collapse' : 'gather'}
            direction={direction}
            transitionDiagnostic={
              waveOnly ? 'waves' : materialOnly ? 'material' : 'beauty'
            }
            ruptureStyle={ruptureStyle}
            accretionStyle={accretionStyle}
            cubeArrival={cubeArrival}
            glitchDiagnostic={glitchDiagnostic}
            waveMode={waveMode}
            streamingWaves={streamingWaves}
            paused={reduced}
            capture={capture}
            onReady={onReady}
            onFailure={onFailure}
            horizonRenderer="relativistic"
            horizonTreatment="limb"
            horizonDiagnostic="beauty"
            diskStyle="turbulent"
            inclination={12}
            bloom={0.28}
          />
        )}
      </div>
      <section
        className="formation-controls"
        aria-label="Motion study controls"
      >
        <p>
          {sequence === 'transition' && accretionStyle !== 'legacy'
            ? {
                split: 'A · split accretion',
                orbit: 'B · orbital capture',
                cascade: 'C · crown then strata',
              }[accretionStyle]
            : sequence === 'transition'
              ? expression === 'force'
                ? ruptureStyle === 'glitch'
                  ? glitchDiagnostic === 'field'
                    ? 'F7 · corruption arrival field'
                    : materialOnly
                      ? 'F7 · source distortion / late fracture'
                      : 'F7 · spreading glitch / mirror fracture'
                  : ruptureStyle === 'mirror'
                    ? streamingWaves
                      ? waveOnly
                        ? 'F6 · coherent smoke-like wave strands'
                        : materialOnly
                          ? 'F6 · fractured source with broad refraction'
                          : 'F6 · mirror fracture / streaming wavefronts'
                      : waveMode === 'spatial'
                        ? waveOnly
                          ? 'F5 · spatial radial filaments'
                          : materialOnly
                            ? 'F5 · fractured source with spatial refraction'
                            : 'F5 · mirror fracture / spatial radiation'
                        : waveOnly
                          ? 'F4 · upright wavefronts only'
                          : materialOnly
                            ? 'F4 · fractured source without wave emission'
                            : 'F4 · mirror fracture / upright wavefronts'
                    : materialOnly
                      ? 'F3 · material transport only · no extra particles or flash'
                      : 'F3 · collapse / material rupture'
                : 'F1 · continuous gathering'
              : sequence === 'cubes'
                ? cubeArrival === 'gravity'
                  ? 'Blue hour · falling accumulation'
                  : 'Blue hour · layered arrival'
                : 'Event horizon · light tracing'}
          <span role="status" aria-live={ready ? 'off' : 'polite'}>
            {failed
              ? 'Graphics unavailable'
              : !ready
                ? 'Preparing the scene…'
                : `${(value * 100).toFixed(0)}% · ${direction.get() > 0 ? 'forward' : 'reverse'}`}
          </span>
        </p>
        <label>
          Progress
          <input
            aria-label="Animation progress"
            type="range"
            min="0"
            max="1"
            step="0.001"
            value={value}
            disabled={!ready || failed || !mounted}
            onChange={(event) => {
              stop();
              progress.set(Number(event.target.value));
            }}
          />
        </label>
        <div className="formation-actions">
          <button
            disabled={!ready || failed || !mounted}
            onClick={() => play(1)}
          >
            {sequence === 'transition' ? 'Play forward' : 'Replay arrival'}
          </button>
          <button
            disabled={!ready || failed || !mounted}
            onClick={() => play(0)}
          >
            Play reverse
          </button>
          <button disabled={!playing} onClick={stop}>
            Pause
          </button>
          <button
            onClick={() => {
              stop();
              setReady(false);
              setFailed(false);
              setMounted((current) => !current);
            }}
          >
            {mounted ? 'Unmount scene' : 'Mount scene'}
          </button>
        </div>
        <small>
          {capture
            ? 'Fixed scene time · deterministic material and camera'
            : 'Live scene time · actual runtime'}
          {reduced ? ' · reduced motion' : ''}
          {expression === 'force'
            ? ' · opposite direction restarts from its source scene'
            : ''}
        </small>
      </section>
    </main>
  );
}
const meta = {
  title: 'Explorations/Scene formation',
  component: FormationStudy,
  render: (args) => (
    <FormationStudy
      key={`${args.sequence ?? 'transition'}-${args.expression ?? 'continuous'}-${args.materialOnly ?? false}-${args.ruptureStyle ?? 'material'}-${args.waveOnly ?? false}-${args.waveMode ?? 'planar'}-${args.streamingWaves ?? false}-${args.accretionStyle ?? 'legacy'}-${args.cubeArrival ?? 'gravity'}`}
      {...args}
    />
  ),
  argTypes: {
    accretionStyle: {
      control: 'radio',
      options: ['legacy', 'split', 'orbit', 'cascade'],
    },
    cubeArrival: { control: 'radio', options: ['gravity', 'layered'] },
    glitchDiagnostic: {
      control: 'radio',
      options: ['beauty', 'field', 'sharp'],
    },
    expression: { control: 'radio', options: ['continuous', 'force'] },
    sequence: { control: 'radio', options: ['transition', 'cubes', 'horizon'] },
    ruptureStyle: {
      control: 'radio',
      options: ['material', 'mirror', 'glitch'],
    },
    waveMode: { control: 'radio', options: ['planar', 'spatial'] },
  },
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
} satisfies Meta<typeof FormationStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const GatherAndForm: Story = {};
export const CollapseAndRupture: Story = { args: { expression: 'force' } };
export const RuptureMaterial: Story = {
  args: { expression: 'force', materialOnly: true },
};
export const MirrorAndWaves: Story = {
  args: { expression: 'force', ruptureStyle: 'mirror' },
};
export const MirrorSurface: Story = {
  args: { expression: 'force', ruptureStyle: 'mirror', materialOnly: true },
};
export const UprightWaves: Story = {
  args: { expression: 'force', ruptureStyle: 'mirror', waveOnly: true },
};
export const RadiatingMirror: Story = {
  args: { expression: 'force', ruptureStyle: 'mirror', waveMode: 'spatial' },
};
export const RadiatingSurface: Story = {
  args: { ...RadiatingMirror.args, materialOnly: true },
};
export const RadiatingWaves: Story = {
  args: { ...RadiatingMirror.args, waveOnly: true },
};
export const StreamingMirror: Story = {
  args: { ...RadiatingMirror.args, streamingWaves: true },
};
export const StreamingSurface: Story = {
  args: { ...StreamingMirror.args, materialOnly: true },
};
export const StreamingWaves: Story = {
  args: { ...StreamingMirror.args, waveOnly: true },
};
export const GlitchAndFracture: Story = {
  args: { expression: 'force', ruptureStyle: 'glitch' },
};
export const GlitchSurface: Story = {
  args: { ...GlitchAndFracture.args, materialOnly: true },
};
export const GlitchField: Story = {
  args: { ...GlitchSurface.args, glitchDiagnostic: 'field' },
};
export const GlitchSharp: Story = {
  args: { ...GlitchSurface.args, glitchDiagnostic: 'sharp' },
};
export const SplitAccretion: Story = {
  args: {
    expression: 'force',
    ruptureStyle: 'glitch',
    accretionStyle: 'split',
  },
};
export const OrbitalAccretion: Story = {
  args: { ...SplitAccretion.args, accretionStyle: 'orbit' },
};
export const CascadeAccretion: Story = {
  args: { ...SplitAccretion.args, accretionStyle: 'cascade' },
};
export const LayeredCubeArrival: Story = {
  args: { sequence: 'cubes', cubeArrival: 'layered' },
};
export const CubeArrival: Story = { args: { sequence: 'cubes' } };
export const HorizonArrival: Story = { args: { sequence: 'horizon' } };
export const PlaybackControls: Story = {
  args: GlitchAndFracture.args,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = canvas.getByRole('button', { name: 'Play reverse' });
    await waitFor(() => expect(button).toBeEnabled(), { timeout: 15000 });
    await userEvent.click(button);
    await waitFor(() =>
      expect(canvas.getByRole('button', { name: 'Pause' })).toBeEnabled(),
    );
    await userEvent.click(canvas.getByRole('button', { name: 'Pause' }));
    await expect(canvas.getByRole('button', { name: 'Pause' })).toBeDisabled();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Unmount scene' }),
    );
    await expect(canvasElement.querySelector('canvas')).toBeNull();
  },
};
