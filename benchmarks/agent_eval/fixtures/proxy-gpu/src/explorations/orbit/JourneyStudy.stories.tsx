import { useCallback, useEffect, useRef, useState } from 'react';
import {
  animate,
  useMotionValue,
  useMotionValueEvent,
  useTransform,
  type AnimationPlaybackControls,
} from 'motion/react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import { MathUtils } from 'three';
import OrbitCanvas from './OrbitCanvas';
import { formationTiming } from './formation';
import './formation-study.css';

const arrivalEnd = formationTiming.cubes;
const forwardStart = arrivalEnd + 3.2;
const forwardEnd = forwardStart + formationTiming.collapse;
const reverseStart = forwardEnd + 3.6;
const reverseEnd = reverseStart + formationTiming.glitch;
const duration = reverseEnd + 3.6;
const phase = (time: number) =>
  time < arrivalEnd
    ? 'Falling arrival'
    : time < forwardStart
      ? 'Cubes running'
      : time < forwardEnd
        ? 'B · orbital accretion'
        : time < reverseStart
          ? 'Horizon running'
          : time < reverseEnd
            ? 'F7 · glitch / fracture'
            : 'Cubes running again';

/** One canvas and one advancing material clock across every boundary. */
function JourneyStudy() {
  const playhead = useMotionValue(0);
  const sceneTime = useTransform(playhead, (time) => 12 + time);
  const entrance = useMotionValue(0);
  const blend = useMotionValue(0);
  const direction = useMotionValue(1);
  const [value, setValue] = useState(0);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const animation = useRef<AnimationPlaybackControls | null>(null);
  const onReady = useCallback(() => setReady(true), []);
  const onFailure = useCallback(() => {
    setFailed(true);
    setPlaying(false);
    animation.current?.stop();
  }, []);
  useMotionValueEvent(playhead, 'change', (time) => {
    entrance.set(Math.min(1, time / arrivalEnd));
    direction.set(time < reverseStart ? 1 : -1);
    blend.set(
      time < reverseStart
        ? MathUtils.clamp(
            (time - forwardStart) / formationTiming.collapse,
            0,
            1,
          )
        : 1 -
            MathUtils.clamp(
              (time - reverseStart) / formationTiming.glitch,
              0,
              1,
            ),
    );
    setValue(time);
  });
  useEffect(() => () => animation.current?.stop(), []);
  const stop = () => {
    animation.current?.stop();
    setPlaying(false);
  };
  return (
    <main
      className="formation-study"
      data-ready={ready}
      data-playing={playing}
      data-phase={phase(value)}
    >
      <div
        className="formation-stage"
        role="img"
        aria-label="Continuous scene journey"
      >
        <OrbitCanvas
          blend={blend}
          entrance={entrance}
          direction={direction}
          sceneTime={sceneTime}
          accretionStyle="orbit"
          study="collapse"
          ruptureStyle="glitch"
          paused
          capture
          onReady={onReady}
          onFailure={onFailure}
          horizonRenderer="relativistic"
          horizonTreatment="limb"
          horizonDiagnostic="beauty"
          diskStyle="turbulent"
          inclination={12}
          bloom={0.28}
        />
      </div>
      <section
        className="formation-controls"
        aria-label="Continuous journey controls"
      >
        <p>
          Continuous journey · selected B
          <span role="status" aria-live="off">
            {failed
              ? 'Graphics unavailable'
              : !ready
                ? 'Preparing the scene…'
                : `${value.toFixed(1)}s · ${phase(value)}`}
          </span>
        </p>
        <label>
          Timeline
          <input
            aria-label="Journey time"
            type="range"
            min="0"
            max={duration}
            step="0.01"
            value={value}
            disabled={!ready || failed}
            onChange={(event) => {
              stop();
              playhead.set(Number(event.target.value));
            }}
          />
        </label>
        <div className="formation-actions">
          <button
            disabled={!ready || failed}
            onClick={() => {
              stop();
              if (playhead.get() >= duration - 0.01) playhead.set(0);
              setPlaying(true);
              animation.current = animate(playhead, duration, {
                duration: duration - playhead.get(),
                ease: 'linear',
                onComplete: () => setPlaying(false),
              });
            }}
          >
            Play journey
          </button>
          <button disabled={!playing} onClick={stop}>
            Pause
          </button>
          <button
            disabled={!ready || failed}
            onClick={() => {
              stop();
              playhead.set(0);
            }}
          >
            Restart
          </button>
        </div>
        <small>
          One canvas · material time advances throughout · no inserted still
          frames · silent visual study
        </small>
      </section>
    </main>
  );
}
const meta = {
  title: 'Explorations/Continuous journey',
  component: JourneyStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
} satisfies Meta<typeof JourneyStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const SelectedB: Story = {};
export const PlaybackControls: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const play = canvas.getByRole('button', { name: 'Play journey' });
    await waitFor(() => expect(play).toBeEnabled(), { timeout: 15000 });
    await userEvent.click(play);
    await userEvent.click(canvas.getByRole('button', { name: 'Pause' }));
    await expect(canvas.getByRole('button', { name: 'Pause' })).toBeDisabled();
    await userEvent.click(canvas.getByRole('button', { name: 'Restart' }));
    await expect(canvas.getByRole('slider')).toHaveValue('0');
  },
};
