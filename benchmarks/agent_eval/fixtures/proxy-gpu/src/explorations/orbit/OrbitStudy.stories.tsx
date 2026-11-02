import type { Meta, StoryObj } from '@storybook/react-vite';
import { expect, userEvent, waitFor, within } from 'storybook/test';
import { OrbitStudy } from './OrbitStudy';
import { previewTracks, resolvePreviewTrack } from '../music-fixtures';
import { sceneTracks } from '../../lib/music/scene-tracks';
import { resolvePublicAudio } from '../../lib/music/sources';
import type { TrackResolver } from '../../lib/music/sources';
import nativeTone from '../audio-fixtures/steady-tone.mp3?url&no-inline';

const failedAudio: TrackResolver = async () => {
  throw new Error('Preview audio unavailable');
};
const delayedAudio: TrackResolver = async (track, signal) => {
  await new Promise((resolve) => setTimeout(resolve, 1200));
  return resolvePreviewTrack(track, signal);
};
const meta = {
  title: 'Explorations/Orbit study',
  component: OrbitStudy,
  parameters: { layout: 'fullscreen', a11y: { test: 'error' } },
  args: {
    initialScene: 'cubes',
    study: 'gather',
    dockDesign: 'classic',
    horizonTreatment: 'optical',
    tracks: { cubes: previewTracks[1]!, horizon: previewTracks[2]! },
    resolve: resolvePreviewTrack,
    horizonRenderer: 'relativistic',
    diskStyle: 'turbulent',
    inclination: 12,
    bloom: 0.28,
    horizonDiagnostic: 'beauty',
  },
  argTypes: {
    horizonDiagnostic: {
      control: 'radio',
      options: ['beauty', 'coordinates', 'emission'],
    },
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
    horizonRenderer: {
      control: 'radio',
      options: ['baseline', 'relativistic'],
    },
    diskStyle: { control: 'radio', options: ['silk', 'turbulent'] },
    inclination: { control: { type: 'range', min: 5, max: 35, step: 1 } },
    bloom: { control: { type: 'range', min: 0, max: 1.2, step: 0.05 } },
  },
} satisfies Meta<typeof OrbitStudy>;
export default meta;
type Story = StoryObj<typeof meta>;
export const SelectedCubes: Story = {
  args: {
    interfaceMode: 'continuous',
    study: 'collapse',
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
    dockDesign: 'drum',
    horizonTreatment: 'limb',
  },
};
export const SelectedHorizon: Story = {
  args: {
    interfaceMode: 'continuous',
    study: 'collapse',
    dockDesign: 'drum',
    horizonTreatment: 'limb',
    initialScene: 'horizon',
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
  },
};
export const SelectedSoundCheck: Story = {
  args: {
    study: 'collapse',
    dockDesign: 'drum',
    horizonTreatment: 'limb',
  },
};
export const BundledSoundCheck: Story = {
  args: {
    ...SelectedSoundCheck.args,
    graphics: 'poster',
    skipEntrance: true,
    resolve: resolvePublicAudio,
    tracks: {
      cubes: { ...previewTracks[1]!, playbackUrl: nativeTone },
      horizon: { ...previewTracks[2]!, playbackUrl: nativeTone },
    },
  },
};
export const ExternalSoundCheck: Story = {
  args: {
    ...BundledSoundCheck.args,
    resolve: async () => ({
      playback: {
        kind: 'audio',
        url: nativeTone,
        analysis: 'unavailable',
      },
    }),
  },
};
export const UnavailableNextTrack: Story = {
  args: {
    ...SelectedSoundCheck.args,
    resolve: async (track, signal) => {
      if (track.id === 'golden-orbit')
        throw new Error('Destination unavailable');
      return resolvePreviewTrack(track, signal);
    },
  },
};
export const HorizonFlowCoordinates: Story = {
  args: {
    ...SelectedHorizon.args,
    skipEntrance: true,
    horizonDiagnostic: 'coordinates',
  },
};
export const HorizonUnbloomedEmission: Story = {
  args: {
    ...SelectedHorizon.args,
    skipEntrance: true,
    horizonDiagnostic: 'emission',
  },
};
export const HorizonBaseline: Story = {
  args: {
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
    initialScene: 'horizon',
    horizonRenderer: 'baseline',
    skipEntrance: true,
  },
};
export const HorizonSilk: Story = {
  args: {
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
    initialScene: 'horizon',
    diskStyle: 'silk',
    skipEntrance: true,
  },
};
export const HorizonTurbulent: Story = {
  args: {
    tracks: sceneTracks,
    resolve: resolvePublicAudio,
    initialScene: 'horizon',
    diskStyle: 'turbulent',
    skipEntrance: true,
  },
};
export const S1Gather: Story = {};
export const S2Vortex: Story = { args: { study: 'vortex' } };
export const HorizonArrival: Story = { args: { initialScene: 'horizon' } };
export const RandomArrival: Story = { args: { initialScene: undefined } };
export const CubesOpen: Story = {
  args: { skipEntrance: true, startOpen: true },
};
export const HorizonOpen: Story = {
  args: { initialScene: 'horizon', skipEntrance: true, startOpen: true },
};
export const StillView: Story = {
  args: { graphics: 'poster', skipEntrance: true, startOpen: true },
};
export const LongMusicMetadata: Story = {
  args: {
    graphics: 'poster',
    skipEntrance: true,
    startOpen: true,
    tracks: {
      cubes: {
        ...previewTracks[1]!,
        title:
          'An unusually long recording title with several movements and variations',
        artist: 'An ensemble with a long list of credited collaborators',
      },
      horizon: previewTracks[2]!,
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    for (let index = 0; index < 2; index++)
      await userEvent.click(canvas.getByRole('button', { name: 'Next card' }));
    await waitFor(() =>
      expect(
        canvas.getByRole('heading', { name: /An unusually long/ }),
      ).toBeVisible(),
    );
  },
};
export const MissingAudio: Story = {
  args: { graphics: 'poster', resolve: failedAudio },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await waitFor(() =>
      expect(
        canvas.getByText('Sound is unavailable. You can continue quietly.'),
      ).toBeVisible(),
    );
    await expect(
      canvas.getByRole('button', { name: 'Enter with sound' }),
    ).toBeDisabled();
    await userEvent.click(
      canvas.getByRole('button', { name: 'Enter quietly' }),
    );
    await waitFor(() =>
      expect(
        canvas.getByRole('button', { name: 'Open information cards' }),
      ).toBeVisible(),
    );
  },
};
export const DelayedAudio: Story = {
  args: { graphics: 'poster', resolve: delayedAudio },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(
      canvas.getByRole('button', { name: 'Enter with sound' }),
    ).toBeDisabled();
    await waitFor(
      () =>
        expect(
          canvas.getByRole('button', { name: 'Enter with sound' }),
        ).toBeEnabled(),
      { timeout: 5000 },
    );
  },
};
export const DeckInteraction: Story = {
  args: { graphics: 'poster', skipEntrance: true },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(
      canvas.getByRole('button', { name: 'Open information cards' }),
    );
    await expect(
      canvas.getByRole('article', { name: 'A little about me' }),
    ).toBeVisible();
    for (
      let index = 0;
      index <
      Number(
        canvasElement
          .querySelector('.orbit-deck')
          ?.getAttribute('data-card-count'),
      ) -
        1;
      index++
    )
      await userEvent.click(canvas.getByRole('button', { name: 'Next card' }));
    await waitFor(() =>
      expect(canvas.getByRole('button', { name: 'Next scene' })).toBeVisible(),
    );
    await expect(
      canvas.getByRole('button', { name: 'Next card' }),
    ).toBeDisabled();
    await userEvent.click(canvas.getByRole('button', { name: 'Next scene' }));
    await waitFor(() =>
      expect(canvasElement.querySelector('main')).toHaveAttribute(
        'data-scene',
        'horizon',
      ),
    );
    await expect(canvasElement.querySelector('main')).toHaveAttribute(
      'data-transitioning',
      'false',
    );
  },
};
