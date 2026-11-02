import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, within, waitFor } from 'storybook/test';
import { MusicPanel } from './MusicPanel';
import { playlist } from '../../lib/content/load';

const meta = {
  title: 'Music/Panel',
  component: MusicPanel,
  args: { playlist },
  decorators: [
    (Story) => (
      <div style={{ position: 'absolute', bottom: 24, left: 16, right: 16 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MusicPanel>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Default: Story = {};
export const Empty: Story = {
  args: { playlist: { defaultTrackId: null, tracks: [] } },
};
export const RapidOpenClose: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    for (let index = 0; index < 3; index++) {
      await userEvent.click(canvas.getByRole('button', { name: 'Listen' }));
      await expect(
        canvas.getByRole('region', { name: 'NetEase player' }),
      ).toBeInTheDocument();
      await userEvent.keyboard('{Escape}');
      await expect(
        canvas.getByRole('button', { name: 'Listen' }),
      ).toHaveFocus();
    }
    await expect(
      canvas.queryByRole('region', { name: 'NetEase player' }),
    ).not.toBeInTheDocument();
  },
};
export const UnavailableEmbed: Story = {
  args: { timeoutMs: 20 },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: 'Listen' }));
    await waitFor(() =>
      expect(canvas.getByRole('status')).toHaveTextContent(
        'If the player is unavailable',
      ),
    );
  },
};

export const MultipleTracks: Story = {
  args: {
    timeoutMs: 1000,
    playlist: {
      defaultTrackId: 'first',
      tracks: [
        {
          id: 'first',
          kind: 'netease-embed',
          songId: '111',
          label: 'First fixture track',
        },
        {
          id: 'second',
          kind: 'netease-embed',
          songId: '222',
          label: 'Second fixture track',
        },
      ],
    },
  },
};
