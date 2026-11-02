import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { OrbitStudy } from './OrbitStudy';

const meta = {
  title: 'Explorations/Card finishes',
  component: OrbitStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: {
    interfaceMode: 'continuous',
    fontStudy: 'plex',
    detailStudy: 'flow',
    graphics: 'poster',
    skipEntrance: true,
    initialScene: 'horizon',
    resolve: async () => {
      throw new Error('Silent material study');
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const deck = await canvas.findByRole('region', {
      name: 'Information slots',
    });
    await userEvent.click(deck);
    await userEvent.keyboard('{ArrowDown}{ArrowDown}');
    const blog = await canvas.findByRole('button', { name: 'Blog' });
    const github = await canvas.findByRole('button', {
      name: 'GitHub',
    });
    await waitFor(() => expect(blog).toBeVisible());
    await waitFor(() => expect(github).toBeVisible());
    await userEvent.hover(blog);
    await userEvent.unhover(blog);
    github.focus();
    await expect(github).toHaveFocus();
    await userEvent.keyboard('{End}');
    await expect(
      canvas.getByRole('button', { name: 'Play music' }),
    ).toBeDisabled();
    await userEvent.keyboard('{Home}');
    await waitFor(() =>
      expect(canvas.getByRole('heading', { name: 'RoyenHeart' })).toBeVisible(),
    );
  },
} satisfies Meta<typeof OrbitStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const InsetGold: Story = { args: { cardFinish: 'inset' } };
export const InsetBlue: Story = {
  args: { cardFinish: 'inset', initialScene: 'cubes' },
};
export const NameplateGold: Story = { args: { cardFinish: 'nameplate' } };
export const NameplateBlue: Story = {
  args: { cardFinish: 'nameplate', initialScene: 'cubes' },
};
export const DriftingInlay: Story = {
  args: { cardFinish: 'nameplate', surfaceMotion: 'drift' },
};
export const LayeredInlay: Story = {
  args: {
    cardFinish: 'nameplate',
    surfaceMotion: 'layers',
    initialScene: 'cubes',
  },
};
export const MovingIllumination: Story = {
  args: { cardFinish: 'nameplate', surfaceMotion: 'light' },
};
export const ElsewhereGlyph: Story = {
  args: { cardFinish: 'nameplate', elsewhereStudy: 'glyph' },
};
export const ElsewhereIndex: Story = {
  args: {
    cardFinish: 'nameplate',
    elsewhereStudy: 'index',
    initialScene: 'cubes',
  },
};
export const ElsewhereTile: Story = {
  args: { cardFinish: 'nameplate', elsewhereStudy: 'tile' },
};
export const SeamGold: Story = { args: { cardFinish: 'seam' } };
export const SeamBlue: Story = {
  args: { cardFinish: 'seam', initialScene: 'cubes' },
};
