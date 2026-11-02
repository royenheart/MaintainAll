import { useLayoutEffect, type RefObject } from 'react';

// Derive line insets from the same SVG silhouette that paints the card.
// Measurements use layout offsets, so a rotating card does not distort its text layout.
export function useContourLayout(
  ref: RefObject<HTMLElement | null>,
  identity: string,
) {
  useLayoutEffect(() => {
    const card = ref.current;
    if (!card) return;
    let active = true;
    let frame = 0;
    const lines = Array.from(
      card.querySelectorAll<HTMLElement>(
        '.orbit-ribbon-copy:not(.orbit-profile) > p, .orbit-ribbon-copy:not(.orbit-profile) > h2, .orbit-profile, .orbit-elsewhere > nav',
      ),
    );
    const update = () => {
      if (!active) return;
      const path = card.querySelector<SVGGeometryElement>(
        '.rotary-surface-base',
      );
      if (!path || !card.clientHeight) return;
      const insetAt = (sampleY: number) => {
        let left = 0,
          right = 150;
        for (let i = 0; i < 12; i++) {
          const middle = (left + right) / 2;
          if (path.isPointInFill(new DOMPoint(middle, sampleY))) right = middle;
          else left = middle;
        }
        return (right / 600) * card.clientWidth + 13;
      };
      const changes = lines.map((line) => {
        let x = 0,
          y = 0;
        let element: HTMLElement | null = line;
        while (element && element !== card) {
          x += element.offsetLeft;
          y += element.offsetTop;
          element = element.offsetParent as HTMLElement | null;
        }
        const sampleY = Math.max(
          3,
          Math.min(97, ((y + line.offsetHeight) / card.clientHeight) * 100),
        );
        const inset = insetAt(sampleY);
        return { line, padding: Math.max(0, inset - x), inset };
      });
      for (const { line, padding, inset } of changes) {
        line.style.paddingLeft = `${padding}px`;
        line.style.setProperty('--contour-padding', `${padding}px`);
        line.dataset.contourInset = inset.toFixed(2);
      }
      const progress = card.querySelector<HTMLElement>(
        '.orbit-ribbon-progress',
      );
      if (progress) {
        // The bottom curve is narrower than the title's slice of the silhouette.
        const sampleY =
          ((progress.offsetTop + progress.offsetHeight) / card.clientHeight) *
          100;
        card.style.setProperty(
          '--contour-progress-start',
          `${insetAt(sampleY)}px`,
        );
      }
    };
    const schedule = () => {
      if (!active) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(card);
    // A responsive title may reappear or reflow without changing the card size.
    for (const line of lines) observer.observe(line);
    update();
    void document.fonts.ready.then(schedule);
    return () => {
      active = false;
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [ref, identity]);
}
