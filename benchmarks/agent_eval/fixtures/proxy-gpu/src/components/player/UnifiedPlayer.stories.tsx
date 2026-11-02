import { useCallback, useRef, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { UnifiedPlayer } from './UnifiedPlayer';
import {
  previewTracks,
  resolvePreviewTrack,
} from '../../explorations/music-fixtures';
import type { ResolvedTrack, TrackResolver } from '../../lib/music/sources';

const localTracks = previewTracks.slice(1);
const meta = {
  title: 'Music/Unified player',
  component: UnifiedPlayer,
  args: { tracks: localTracks, resolveTrack: resolvePreviewTrack },
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#f7f9fb', minHeight: '100dvh' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof UnifiedPlayer>;
export default meta;
type Story = StoryObj<typeof meta>;
export const LocalAudio: Story = {};
export const Empty: Story = { args: { tracks: [] } };
export const SpotifyConnection: Story = {
  args: {
    tracks: [
      {
        id: 'spotify-example',
        title: 'A track from Spotify',
        artist: 'Connection required',
        source: { provider: 'spotify', id: '4cOdK2wGLETKBW3PvgPWqT' },
      },
    ],
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() =>
      expect(canvas.getByRole('status')).toHaveTextContent('Connect Spotify'),
    );
    await expect(
      canvas.getByRole('button', { name: 'Play music' }),
    ).toBeDisabled();
    await expect(
      canvas.getByRole('link', { name: /Open source/ }),
    ).toHaveAttribute(
      'href',
      'https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT',
    );
    await expect(canvasElement.querySelector('iframe')).toBeNull();
  },
};
export const LongMetadata: Story = {
  args: {
    tracks: [
      {
        ...localTracks[0]!,
        title:
          'A very long movement title that should remain readable without pushing playback controls out of the frame',
        artist:
          'A large collection of collaborators and orchestral performers with an unusually long credit',
      },
      localTracks[1]!,
    ],
  },
};
export const TrackAndVolumeControls: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: 'Next track' }));
    await expect(canvas.getByText('Golden Orbit')).toBeInTheDocument();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Previous track' }),
    );
    await expect(canvas.getByText('Blue Hour')).toBeInTheDocument();
    await userEvent.click(canvas.getByRole('button', { name: 'Mute music' }));
    await expect(canvasElement.querySelector('audio')!.muted).toBe(true);
    await expect(canvasElement.querySelectorAll('audio')).toHaveLength(1);
    await expect(canvasElement.querySelector('iframe')).toBeNull();
  },
};

export const RapidQueueWrap: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const next = canvas.getByRole('button', { name: 'Next track' });
    // Batched input returns to the same track ID but still owns a fresh resolution.
    for (let i = 0; i < 6; i++) next.click();
    await waitFor(() =>
      expect(canvas.getByText('Blue Hour')).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(canvas.getByRole('button', { name: 'Play music' })).toBeEnabled(),
    );
    await expect(canvasElement.querySelectorAll('audio')).toHaveLength(1);
  },
};

function DeferredPlayer() {
  const pending = useRef<((result: ResolvedTrack) => void)[]>([]);
  const [visible, setVisible] = useState(true);
  const [aborted, setAborted] = useState(0);
  const resolver = useCallback<TrackResolver>(
    (_track, signal) =>
      new Promise((resolve) => {
        pending.current.push(resolve);
        signal.addEventListener(
          'abort',
          () => setAborted((count) => count + 1),
          { once: true },
        );
      }),
    [],
  );
  return (
    <>
      {visible && (
        <UnifiedPlayer tracks={localTracks} resolveTrack={resolver} />
      )}
      <div
        style={{ marginTop: 32, display: 'flex', flexWrap: 'wrap', gap: 16 }}
      >
        <button
          onClick={() =>
            pending.current[0]?.({
              title: 'Stale metadata',
              playback: { kind: 'external', message: 'Stale request' },
            })
          }
        >
          Resolve first request
        </button>
        <button
          onClick={() =>
            pending.current[1]?.({
              title: 'Current metadata',
              playback: { kind: 'external', message: 'Current request' },
            })
          }
        >
          Resolve second request
        </button>
        <button onClick={() => setVisible(false)}>Unmount player</button>
        <span>Aborted requests: {aborted}</span>
      </div>
    </>
  );
}

export const StaleResolution: Story = {
  render: () => <DeferredPlayer />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: 'Next track' }));
    await expect(canvas.getByText('Aborted requests: 1')).toBeInTheDocument();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Resolve second request' }),
    );
    await waitFor(() =>
      expect(canvas.getByText('Current metadata')).toBeInTheDocument(),
    );
    await userEvent.click(
      canvas.getByRole('button', { name: 'Resolve first request' }),
    );
    await expect(canvas.queryByText('Stale metadata')).not.toBeInTheDocument();
    await expect(canvas.getByRole('status')).toHaveTextContent(
      'Current request',
    );
  },
};
export const ResolveAfterUnmount: Story = {
  render: () => <DeferredPlayer />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole('button', { name: 'Unmount player' }),
    );
    await expect(canvas.getByText('Aborted requests: 1')).toBeInTheDocument();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Resolve first request' }),
    );
    await expect(
      canvas.queryByRole('region', { name: 'Music player' }),
    ).not.toBeInTheDocument();
    await expect(canvasElement.querySelector('audio')).toBeNull();
  },
};
