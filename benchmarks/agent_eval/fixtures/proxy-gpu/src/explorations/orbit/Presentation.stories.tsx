import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { OrbitStudy } from './OrbitStudy';
import { CoverLab } from './CoverLab';
import { presentationStudies } from './presentation';
import { sceneTracks } from '../../lib/music/scene-tracks';

const meta = {
  title: 'Explorations/Continuous presentation',
  component: OrbitStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: {
    interfaceMode: 'continuous',
    graphics: 'poster',
    initialScene: 'horizon',
    tracks: sceneTracks,
    resolve: async () => {
      throw new Error('Silent layout study');
    },
  },
} satisfies Meta<typeof OrbitStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const A: Story = {
  args: {
    fontStudy: presentationStudies.a.font,
    coverStudy: presentationStudies.a.cover,
    identityStudy: presentationStudies.a.identity,
  },
};
export const B: Story = {
  args: {
    fontStudy: presentationStudies.b.font,
    coverStudy: presentationStudies.b.cover,
    identityStudy: presentationStudies.b.identity,
  },
};
export const C: Story = {
  args: {
    fontStudy: presentationStudies.c.font,
    coverStudy: presentationStudies.c.cover,
    identityStudy: presentationStudies.c.identity,
  },
};
export const PersistentNavigation: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const deck = await canvas.findByRole('region', {
      name: 'Information slots',
    });
    await expect(
      canvas.queryByRole('button', { name: 'Enter quietly' }),
    ).toBeNull();
    await userEvent.click(deck);
    await userEvent.keyboard('{ArrowDown}');
    await waitFor(() =>
      expect(
        canvas.getByRole('navigation', { name: 'Music platforms' }),
      ).toBeVisible(),
    );
    await waitFor(() =>
      expect(
        canvas.getByRole('link', { name: 'Open on Spotify' }),
      ).toBeVisible(),
    );
    await userEvent.keyboard('{ArrowDown}');
    await waitFor(() =>
      expect(
        canvas.getByRole('navigation', { name: 'Elsewhere' }),
      ).toBeVisible(),
    );
    await userEvent.keyboard('{Escape}');
    await expect(deck).toBeVisible();
    await expect(
      canvas.getByRole('button', { name: 'Focus identity card' }),
    ).toHaveFocus();
  },
};
export const ArtworkMaterials: Story = { render: () => <CoverLab /> };

export const EtchedDetails: Story = {
  args: { fontStudy: 'plex', detailStudy: 'etch', skipEntrance: true },
  play: PersistentNavigation.play,
};
export const FlowDetails: Story = {
  args: { fontStudy: 'plex', detailStudy: 'flow', skipEntrance: true },
  play: PersistentNavigation.play,
};
export const ArcDetails: Story = {
  args: { fontStudy: 'plex', detailStudy: 'orbit', skipEntrance: true },
  play: PersistentNavigation.play,
};

export const GlideRails: Story = {
  args: {
    cardFinish: 'original',
    fontStudy: 'plex',
    detailStudy: 'flow',
    railStudy: 'glide',
    skipEntrance: true,
  },
  play: PersistentNavigation.play,
};
export const TetherRails: Story = {
  args: {
    cardFinish: 'original',
    fontStudy: 'plex',
    detailStudy: 'flow',
    railStudy: 'tether',
    skipEntrance: true,
  },
  play: PersistentNavigation.play,
};
export const RelayRails: Story = {
  args: {
    cardFinish: 'original',
    fontStudy: 'plex',
    detailStudy: 'flow',
    railStudy: 'relay',
    skipEntrance: true,
  },
  play: PersistentNavigation.play,
};
