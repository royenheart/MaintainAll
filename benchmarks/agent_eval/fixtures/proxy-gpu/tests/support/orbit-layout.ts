// Serialized into each browser to inspect the rendered layout, including dynamic cards.
export function inspectOrbitLayout() {
  const issues: string[] = [];
  const root = document.querySelector<HTMLElement>('.orbit-study');
  if (!root) return ['Missing orbit study'];
  const rect = (node: Element) => node.getBoundingClientRect();
  const visible = (node: Element) =>
    rect(node).width > 0 &&
    rect(node).height > 0 &&
    Number(getComputedStyle(node).opacity) > 0.05 &&
    !node.closest('[inert], [aria-hidden="true"]');
  const contains = (parent: Element, child: Element) => {
    const p = rect(parent),
      c = rect(child);
    if (
      c.left < p.left - 2 ||
      c.top < p.top - 2 ||
      c.right > p.right + 2 ||
      c.bottom > p.bottom + 2
    )
      issues.push(
        `${child.className || child.textContent?.trim()} escapes ${parent.className}`,
      );
  };
  const overlap = (a: Element, b: Element) => {
    const x = rect(a),
      y = rect(b);
    if (
      a.matches('.orbit-disc, .orbit-sound') &&
      b.matches('.orbit-disc, .orbit-sound')
    ) {
      return (
        Math.hypot(
          x.x + x.width / 2 - y.x - y.width / 2,
          x.y + x.height / 2 - y.y - y.height / 2,
        ) <
        (x.width + y.width) / 2 - 2
      );
    }
    const round = a.matches('.orbit-disc, .orbit-sound')
      ? x
      : b.matches('.orbit-disc, .orbit-sound')
        ? y
        : null;
    if (round) {
      const box = round === x ? y : x;
      const cx = round.x + round.width / 2,
        cy = round.y + round.height / 2;
      const nearestX = Math.max(box.left, Math.min(cx, box.right));
      const nearestY = Math.max(box.top, Math.min(cy, box.bottom));
      return Math.hypot(cx - nearestX, cy - nearestY) < round.width / 2 - 2;
    }
    return (
      Math.min(x.right, y.right) - Math.max(x.left, y.left) > 2 &&
      Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 2
    );
  };
  const controls = Array.from(root.querySelectorAll('button, a')).filter(
    visible,
  );
  for (const element of controls) {
    contains(root, element);
    const r = rect(element);
    const insetPlayback = root.dataset.dockDesign !== 'classic';
    const hit = document.elementFromPoint(
      r.x +
        (insetPlayback && element.matches('.orbit-disc') ? 12 : r.width / 2),
      r.y + r.height / 2,
    );
    if (!hit || !element.contains(hit))
      issues.push(
        `Control is occluded: ${element.getAttribute('aria-label') ?? element.textContent}`,
      );
  }
  for (const [index, control] of controls.entries())
    for (const other of controls.slice(index + 1)) {
      // The playback button intentionally overlays the artwork, inside its circle.
      if (
        root.dataset.dockDesign !== 'classic' &&
        control.matches('.orbit-disc, .orbit-sound') &&
        other.matches('.orbit-disc, .orbit-sound')
      )
        continue;
      if (overlap(control, other))
        issues.push(
          `Controls overlap: ${control.getAttribute('aria-label') ?? control.textContent} / ${other.getAttribute('aria-label') ?? other.textContent}`,
        );
    }
  const front = root.querySelector('.orbit-card-front:not([inert])');
  const heading = root.querySelector('.orbit-heading')!;
  if (front) {
    contains(root, front);
    const cover = rect(root.querySelector('.orbit-artwork')!);
    const cx = cover.x + cover.width / 2,
      cy = cover.y + cover.height / 2;
    for (const ribbon of root.querySelectorAll('.orbit-card')) {
      const r = rect(ribbon);
      if (r.top < cover.top - 1 || r.bottom > cover.bottom + 1)
        issues.push('Ribbon escapes the artwork height');
      if (r.height > cover.height * 0.51)
        issues.push('Ribbon is too tall for the compact artwork');
      const shape = getComputedStyle(ribbon).clipPath;
      const cut = Number(shape.match(/, ([\d.]+)px 100%\)$/)?.[1]);
      if (!Number.isFinite(cut)) {
        issues.push('Unmeasurable trapezoid outline');
        continue;
      }
      const corners = [
        [r.right - 1, r.top + 1],
        [r.right - cut, r.bottom - 1],
      ];
      for (const [x, y] of corners) {
        if (Math.hypot(x! - cx, y! - cy) > cover.width / 2 - 1)
          issues.push('Trapezoid seam is outside the artwork circle');
        if (!document.elementFromPoint(x!, y!)?.closest('.orbit-disc'))
          issues.push('Artwork does not occlude the trapezoid seam');
      }
    }
    if (!getComputedStyle(front).clipPath.startsWith('polygon('))
      issues.push('Card is missing its trapezoid silhouette');
    for (const content of front.children)
      if (visible(content)) contains(front, content);
    if (overlap(front, heading)) issues.push('Card overlaps scene heading');
  }
  const wheel = root.querySelector('.orbit-wheel');
  const wheelLimit =
    root.dataset.dockDesign === 'classic'
      ? innerWidth < 640
        ? 125
        : 165
      : innerWidth < 640
        ? 137
        : 153;
  if (wheel && rect(wheel).width > wheelLimit)
    issues.push('Wheel exceeds its compact size budget');
  const canvas = root.querySelector('canvas');
  if (
    canvas &&
    (Math.abs(rect(canvas).width - rect(root).width) > 2 ||
      Math.abs(rect(canvas).height - rect(root).height) > 2)
  )
    issues.push('Canvas does not match viewport');
  if (
    document.documentElement.scrollWidth > innerWidth + 2 ||
    document.documentElement.scrollHeight > innerHeight + 2
  )
    issues.push('Document overflows');
  const registrations = root.querySelector('.orbit-dock-registrations');
  if (registrations) {
    const footer = rect(registrations);
    const deck = rect(root.querySelector('.rotary-deck')!);
    const artwork = rect(root.querySelector('.orbit-artwork')!);
    if (footer.top < Math.max(deck.bottom, artwork.bottom) + 4)
      issues.push('Registrations collide with the cards or artwork');
    if (Math.abs(footer.left - deck.left) > 2)
      issues.push('Registrations are not aligned beneath the deck');
    if (Math.abs(footer.right - artwork.right) > 2)
      issues.push('Registration rule does not align with the visible cover');
    const links = Array.from(registrations.querySelectorAll('a'));
    if (links.length && Math.abs(rect(links.at(-1)!).right - footer.right) > 2)
      issues.push('Registration text is not right aligned');
    if (
      links.length > 1 &&
      Math.abs(rect(links[0]!).top - rect(links[1]!).top) > 1
    )
      issues.push('Registrations wrap into multiple rows');
    if (footer.height > 46)
      issues.push('Registration row exceeds its compact height');
    contains(root, registrations);
    for (const link of registrations.querySelectorAll('a')) {
      contains(registrations, link);
      if (rect(link).height < 44)
        issues.push('Registration target is too short');
      const label = link.querySelector('span')!;
      if (label.scrollWidth > label.clientWidth + 1)
        issues.push('Registration text is clipped');
    }
  }
  return issues;
}
