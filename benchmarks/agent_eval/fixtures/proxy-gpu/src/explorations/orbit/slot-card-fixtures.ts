import type { SiteContent } from '../../lib/content/schema';

/** Explicit review-only content, never included in the real link list. */
export const slotCardSamples: SiteContent['links'] = Array.from(
  { length: 8 },
  (_, index) => ({
    label: `Sample ${index + 1}`,
    href: `https://example.org/card-${index + 1}`,
    preview: {
      identity: `Interaction study · ${index + 1} / 8`,
      description:
        index === 4
          ? 'A longer sample checks wrapping, nested scrolling and the card lip on short screens.'
          : 'Sample content for the independently scrollable card group.',
      topics: ['Study', 'Sample'],
    },
  }),
);
