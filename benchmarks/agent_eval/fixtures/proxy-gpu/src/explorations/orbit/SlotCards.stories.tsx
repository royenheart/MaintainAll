import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { slotCardSamples } from './slot-card-fixtures';
import { OrbitStudy } from './OrbitStudy';

const meta = {
  title: 'Explorations/Slot cards',
  component: OrbitStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: {
    interfaceMode: 'continuous',
    initialCard: 'elsewhere',
    cardFinish: 'nameplate',
    surfaceMotion: 'drift',
    elsewhereStudy: 'tile',
    cardMaterial: 'drift',
    graphics: 'poster',
    skipEntrance: true,
    initialScene: 'horizon',
    resolve: async () => {
      throw new Error('Silent slot study');
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const blog = await canvas.findByRole('button', { name: 'Blog' });
    const github = canvas.getByRole('button', { name: 'GitHub' });
    await userEvent.hover(blog);
    await waitFor(() =>
      expect(
        canvas.getByRole('group', { name: 'Current card' }),
      ).toHaveAttribute('data-state', 'open'),
    );
    await expect(
      canvasElement.querySelectorAll('.slot-card-stack i'),
    ).toHaveLength(1);
    await expect(
      canvasElement.querySelectorAll('.slot-card-rear'),
    ).toHaveLength(0);
    await userEvent.unhover(blog);
    await userEvent.hover(github);
    await waitFor(() =>
      expect(
        canvas.getByRole('group', { name: 'Current card' }),
      ).toHaveTextContent('@royenheart'),
    );
    await waitFor(() =>
      expect(
        canvas.getByRole('group', { name: 'Current card' }),
      ).toHaveAttribute('data-state', 'open'),
    );
    await expect(
      canvas.getByRole('group', { name: 'Current card' }),
    ).not.toHaveTextContent('github.com');
    await userEvent.keyboard('{Escape}');
    await waitFor(() =>
      expect(canvas.queryByRole('group', { name: 'Current card' })).toBeNull(),
    );
  },
} satisfies Meta<typeof OrbitStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const StraightExtraction: Story = { args: { cardExtraction: 'slide' } };
export const LiftAndSettle: Story = { args: { cardExtraction: 'lift' } };
export const StaggeredHandoff: Story = { args: { cardExtraction: 'fan' } };
export const InlayDrift: Story = {
  args: { cardMaterial: 'drift', initialScene: 'cubes' },
};
export const SoftLight: Story = {
  args: { cardMaterial: 'light', initialScene: 'cubes' },
};
export const LayeredDrift: Story = {
  args: { cardMaterial: 'layers', initialScene: 'cubes' },
};

export const EngravedScene: Story = {
  args: { cardArt: 'engraving', initialScene: 'cubes' },
};
export const IrregularFoil: Story = { args: { cardArt: 'foil' } };
export const LayeredRelief: Story = {
  args: { cardArt: 'relief', initialScene: 'cubes' },
};

export const FoilEmblems: Story = { args: { elsewhereMark: 'emblem' } };
export const IntaglioBookmarks: Story = {
  args: { elsewhereMark: 'intaglio', initialScene: 'cubes' },
};
export const EditorialPrints: Story = { args: { elsewhereMark: 'editorial' } };

export const EightBoundCards: Story = {
  args: { elsewhereLinks: slotCardSamples },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      await canvas.findByRole('button', { name: 'Sample 6' }),
    );
    await waitFor(() =>
      expect(
        canvas.getByRole('group', { name: 'Current card' }),
      ).toHaveTextContent('Sample 6'),
    );
    const region = canvas.getByRole('region', { name: 'Elsewhere cards' });
    region.focus();
    await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
    await waitFor(() => expect(region).toHaveAttribute('data-card-index', '0'));
    await waitFor(() =>
      expect(
        canvas.getByRole('group', { name: 'Current card' }),
      ).toHaveTextContent('Sample 1'),
    );
    await userEvent.keyboard('{Escape}');
    await waitFor(() =>
      expect(canvas.queryByRole('group', { name: 'Current card' })).toBeNull(),
    );
  },
};
