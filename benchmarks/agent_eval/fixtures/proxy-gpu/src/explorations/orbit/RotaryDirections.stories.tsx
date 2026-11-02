import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import { OrbitStudy } from './OrbitStudy';
import { sceneTracks } from '../../lib/music/scene-tracks';
import {
  previewTracks,
  resolvePreviewTrack,
  resolveSilentPreviewTrack,
} from '../music-fixtures';
import { resolvePublicAudio } from '../../lib/music/sources';

const meta = {
  title: 'Explorations/Rotary directions',
  component: OrbitStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: {
    initialScene: 'horizon',
    skipEntrance: true,
    startOpen: true,
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
    cardDuration: 0.68,
  },
  argTypes: {
    horizonTreatment: {
      type: 'string',
      control: 'radio',
      options: ['optical', 'limb'],
    },
    dockDesign: {
      type: 'string',
      control: 'radio',
      options: ['classic', 'tangent', 'drum', 'orbit'],
    },
    cardDuration: {
      control: { type: 'range', min: 0.35, max: 1.2, step: 0.05 },
    },
  },
} satisfies Meta<typeof OrbitStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const TangentGlass: Story = { args: { dockDesign: 'tangent' } };
export const VelvetDrum: Story = { args: { dockDesign: 'drum' } };
export const OrbitalRibbon: Story = { args: { dockDesign: 'orbit' } };
export const TangentCubes: Story = {
  args: { dockDesign: 'tangent', initialScene: 'cubes' },
};
export const DrumCubes: Story = {
  args: { dockDesign: 'drum', initialScene: 'cubes' },
};
export const OrbitalCubes: Story = {
  args: { dockDesign: 'orbit', initialScene: 'cubes' },
};
export const InterruptedDrum: Story = {
  args: { dockDesign: 'drum', graphics: 'poster' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    canvas.getByRole('region', { name: 'Information cards' }).focus();
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowUp}');
    await waitFor(() =>
      expect(canvasElement.querySelector('.rotary-deck')).toHaveAttribute(
        'data-moving',
        'false',
      ),
    );
    await expect(canvas.getByRole('article')).toHaveAccessibleName(
      'On the turntable',
    );
    await userEvent.keyboard('{Escape}');
    await expect(
      canvas.getByRole('button', { name: 'Open information cards' }),
    ).toHaveFocus();
  },
};

export const NativeDrum: Story = {
  args: {
    dockDesign: 'drum',
    graphics: 'poster',
    tracks: { cubes: previewTracks[1]!, horizon: previewTracks[2]! },
    resolve: resolvePreviewTrack,
  },
};

export const SilentDrum: Story = {
  args: {
    ...NativeDrum.args,
    resolve: resolveSilentPreviewTrack,
    tracks: {
      cubes: { ...previewTracks[1]!, title: 'Silent audio fixture' },
      horizon: { ...previewTracks[2]!, title: 'Silent audio fixture' },
    },
  },
};
