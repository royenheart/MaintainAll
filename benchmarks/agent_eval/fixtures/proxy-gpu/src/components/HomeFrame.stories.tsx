import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within } from 'storybook/test';
import { HomeFrame } from './HomeFrame';
import { MusicPanel } from './music/MusicPanel';
import { SceneExperience } from './scene/SceneExperience';
import { site, playlist, scenes } from '../lib/content/load';
import avatar from '../assets/avatar.webp?url';
import cubes from '../assets/cubes.webp?url';
import horizon from '../assets/horizon.webp?url';
import { inspectLayout } from '../../tests/support/layout';

const meta = {
  title: 'Page/Home frame',
  component: HomeFrame,
  args: {
    site,
    avatar,
    scene: (
      <SceneExperience
        settings={scenes}
        posters={{ cubes, horizon }}
        graphics="poster"
      />
    ),
    music: <MusicPanel playlist={playlist} />,
  },
  parameters: { layout: 'fullscreen' },
  tags: ['autodocs'],
} satisfies Meta<typeof HomeFrame>;
export default meta;
type Story = StoryObj<typeof meta>;

const check: Story['play'] = async ({ canvasElement }) => {
  await expect(inspectLayout(canvasElement).issues).toEqual([]);
  const canvas = within(canvasElement);
  await userEvent.click(canvas.getByRole('button', { name: 'Switch scene' }));
  await expect(canvas.getByText('Golden event horizon')).toBeInTheDocument();
  await expect(inspectLayout(canvasElement).issues).toEqual([]);
};
export const Desktop: Story = {
  play: check,
  globals: { viewport: { value: 'desktop' } },
};
export const Phone: Story = {
  play: check,
  globals: { viewport: { value: 'phone' } },
};
export const CompactPhone: Story = {
  play: check,
  globals: { viewport: { value: 'compact' } },
};
export const Tablet: Story = {
  play: check,
  globals: { viewport: { value: 'tablet' } },
};
export const ShortLandscape: Story = {
  play: check,
  globals: { viewport: { value: 'short' } },
};
export const EmptyPlaylist: Story = {
  args: {
    music: <MusicPanel playlist={{ defaultTrackId: null, tracks: [] }} />,
  },
  play: check,
};
export const LongTrack: Story = {
  args: {
    music: (
      <MusicPanel
        playlist={{
          defaultTrackId: 'long',
          tracks: [
            {
              id: 'long',
              kind: 'netease-embed',
              songId: '30953026',
              label:
                'A very long recording title with uninterruptedwordsandnumbers0123456789 that must not displace the registration links',
            },
          ],
        }}
      />
    ),
  },
  play: check,
};
