import type { Meta, StoryObj } from '@storybook/react-vite';
import { DesignConcept } from './DesignConcept';

const meta = {
  title: 'Explorations/Design directions',
  component: DesignConcept,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: { direction: 'orbital', graphics: 'auto' },
} satisfies Meta<typeof DesignConcept>;
export default meta;
type Story = StoryObj<typeof meta>;
export const OrbitalConsole: Story = {};
export const LiquidChrome: Story = { args: { direction: 'liquid' } };
export const QuietGallery: Story = { args: { direction: 'gallery' } };
export const PopCircuit: Story = { args: { direction: 'pop' } };
