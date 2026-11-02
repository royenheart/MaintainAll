export function inspectRotaryLayout() {
  const issues: string[] = [];
  const root = document.querySelector<HTMLElement>('.orbit-study')!;
  if (!root) return ['Missing orbit study'];
  const deck = root.querySelector<HTMLElement>('.rotary-deck')!;
  const card = root.querySelector<HTMLElement>('.rotary-card-active')!;
  if (!deck || !card) return ['Missing rotary deck'];
  const c = card.getBoundingClientRect();
  const cover = root.querySelector('.orbit-artwork')!.getBoundingClientRect();
  const wheel = root.querySelector('.orbit-wheel')!.getBoundingClientRect();
  // Bars can reach radius 106 in a 200-unit SVG; include the stroke and gap.
  const responseLimit = wheel.left - wheel.width * 0.035 - 8;
  const cx = cover.x + cover.width / 2,
    cy = cover.y + cover.height / 2;
  if (
    c.left < -1 ||
    c.right > innerWidth + 1 ||
    c.top < 0 ||
    c.bottom > innerHeight
  )
    issues.push('Active card escapes the viewport');
  if (c.top < cover.top - 2 || c.bottom > cover.bottom + 2)
    issues.push('Settled card exceeds the artwork height');
  if (root.dataset.dockDesign === 'tangent' && Math.abs(c.top - cover.top) > 2)
    issues.push('Tangent card does not align with the artwork top');
  if (c.height < 44 || c.height > cover.height * 0.65)
    issues.push('Card height violates the candidate proportion');
  for (const [x, y] of [
    [c.right - 2, c.top + 6],
    [c.right - 3, c.bottom - 6],
  ]) {
    if (Math.hypot(x! - cx, y! - cy) > cover.width / 2)
      issues.push('Card attachment escapes the artwork');
    if (
      !document.elementFromPoint(x!, y!)?.closest('.orbit-disc, .orbit-sound')
    )
      issues.push('Artwork does not cover the card attachment');
  }
  for (const element of card.querySelectorAll<HTMLElement>(
    'a, button, .orbit-ribbon-copy',
  )) {
    const r = element.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (
      r.left < c.left - 1 ||
      r.right > cover.left + 2 ||
      r.top < c.top - 1 ||
      r.bottom > c.bottom + 1
    )
      issues.push('Card content collides with its outline or artwork');
    if (element.matches('a,button') && r.height < 43)
      issues.push('Card control has an undersized touch target');
    if (root.dataset.interface === 'continuous' && r.right > responseLimit + 1)
      issues.push('Card content enters the audio response clearance');
  }
  const surface = card.querySelector('svg')!;
  const outline = surface.querySelector<SVGGeometryElement>(
    '.rotary-surface-base',
  )!;
  const progress = card.querySelector('progress');
  if (progress) {
    const box = progress.getBoundingClientRect();
    // Check a 2px breathing space, not just the rectangular card bounds.
    for (const x of [box.left - 2, box.right + 2]) {
      for (const y of [box.top - 2, box.bottom + 2]) {
        if (
          !outline.isPointInFill(
            new DOMPoint(
              ((x - c.left) / c.width) * 600,
              ((y - c.top) / c.height) * 100,
            ),
          )
        )
          issues.push('Song progress escapes the painted contour clearance');
      }
    }
  }
  for (const line of card.querySelectorAll<HTMLElement>(
    '.orbit-ribbon-copy:not(.orbit-profile) > p, .orbit-ribbon-copy:not(.orbit-profile) > h2, .orbit-profile',
  )) {
    const box = line.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    const textX =
      box.left - c.left + parseFloat(getComputedStyle(line).paddingLeft);
    const y = Math.max(
      3,
      Math.min(97, ((box.bottom - c.top) / c.height) * 100),
    );
    const near = new DOMPoint(((textX - 5) / c.width) * 600, y);
    const far = new DOMPoint(((textX - 21) / c.width) * 600, y);
    if (!outline.isPointInFill(near) || outline.isPointInFill(far))
      issues.push('Text line does not follow the painted contour');
  }
  const profile = card.querySelector('.orbit-profile');
  if (profile) {
    const avatar = profile.querySelector('img')!.getBoundingClientRect();
    const name = profile.querySelector('h2')!.getBoundingClientRect();
    if (avatar.right + 5 > name.left || avatar.height < 28)
      issues.push('Profile avatar and name collide or shrink excessively');
    if (avatar.top < c.top || avatar.bottom > c.bottom)
      issues.push('Profile avatar escapes the card');
    if (profile.querySelector('h2')!.scrollWidth > name.width + 1)
      issues.push('Profile name is clipped');
  }
  if (surface.querySelectorAll('path, ellipse, circle').length < 30)
    issues.push('Procedural surface texture is absent');
  if (
    root.querySelector('.orbit-monogram') ||
    root.querySelector('.orbit-heading p')
  )
    issues.push('Upper-left branding remains');
  return issues;
}
