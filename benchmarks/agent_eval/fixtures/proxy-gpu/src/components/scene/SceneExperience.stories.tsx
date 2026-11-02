import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { SceneExperience } from './SceneExperience';
import { scenes } from '../../lib/content/load';
import cubes from '../../assets/cubes.webp?url';
import horizon from '../../assets/horizon.webp?url';

const meta = {
  title: 'Scene/Experience',
  component: SceneExperience,
  args: { settings: scenes, posters: { cubes, horizon }, graphics: 'poster' },
  decorators: [
    (Story) => (
      <div style={{ position: 'relative', height: '100dvh', minHeight: 240 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SceneExperience>;
export default meta;
type Story = StoryObj<typeof meta>;
export const RapidSwitching: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const button = canvas.getByRole('button', { name: 'Switch scene' });
    for (let index = 0; index < 21; index++) await userEvent.click(button);
    await expect(canvas.getByText('Golden event horizon')).toBeInTheDocument();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Pause animation' }),
    );
    await expect(
      canvas.getByRole('button', { name: 'Resume animation' }),
    ).toHaveAttribute('aria-pressed', 'true');
  },
};
export const GraphicsFailure: Story = {
  args: {
    graphics: 'auto',
    loadGraphics: () => Promise.reject(new Error('Simulated chunk failure')),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() =>
      expect(canvas.getByRole('status')).toHaveTextContent(
        'graphics unavailable',
      ),
    );
    await userEvent.click(canvas.getByRole('button', { name: 'Switch scene' }));
    await expect(canvas.getByText('Golden event horizon')).toBeInTheDocument();
  },
};

function DelayedHarness() {
  const [mounted, setMounted] = useState(true);
  const [resolve, setResolve] = useState<(() => void) | null>(null);
  const [load] = useState(
    () => () =>
      new Promise<{ default: typeof FakeCanvas }>((done) =>
        setResolve(() => () => done({ default: FakeCanvas })),
      ),
  );
  return (
    <>
      <div
        style={{
          position: 'absolute',
          zIndex: 10,
          top: 12,
          left: 12,
          background: 'white',
          padding: 12,
        }}
      >
        <button onClick={() => setMounted(false)}>Unmount scene</button>{' '}
        <button onClick={() => resolve?.()}>Resolve graphics</button>
      </div>
      {mounted && (
        <SceneExperience
          settings={scenes}
          posters={{ cubes, horizon }}
          graphics="auto"
          loadGraphics={load}
        />
      )}
    </>
  );
}
function FakeCanvas({ scene }: { scene: string }) {
  return <div data-testid="loaded-graphics">{scene}</div>;
}
export const UnmountBeforeLoad: Story = {
  render: () => <DelayedHarness />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole('button', { name: 'Unmount scene' }),
    );
    await userEvent.click(
      canvas.getByRole('button', { name: 'Resolve graphics' }),
    );
    await expect(
      canvas.queryByTestId('loaded-graphics'),
    ).not.toBeInTheDocument();
    await expect(
      canvas.queryByRole('button', { name: 'Switch scene' }),
    ).not.toBeInTheDocument();
  },
};
export const SwitchBeforeLoad: Story = {
  render: () => <DelayedHarness />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: 'Switch scene' }));
    await userEvent.click(
      canvas.getByRole('button', { name: 'Resolve graphics' }),
    );
    await waitFor(() =>
      expect(canvas.getByTestId('loaded-graphics')).toHaveTextContent(
        'horizon',
      ),
    );
  },
};
