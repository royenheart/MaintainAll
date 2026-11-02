/** Only visible text is tested: short screens intentionally scroll inside cards. */
export function inspectSlotCard(): string[] {
  const card = document.querySelector<HTMLElement>(
    '.elsewhere-preview[data-state="open"]',
  );
  const slot = document.querySelector('.rotary-card-active');
  const aperture = card?.closest('.slot-card-aperture');
  const wheel = document.querySelector('.orbit-wheel');
  if (!card || !slot || !aperture || !wheel) return ['Missing open bound card'];
  const errors: string[] = [];
  const c = card.getBoundingClientRect(),
    s = slot.getBoundingClientRect(),
    a = aperture.getBoundingClientRect(),
    w = wheel.getBoundingClientRect();
  if (Math.abs(c.bottom - s.top - 8) > 1.5)
    errors.push('Card detached from its source lip');
  if (Math.abs(a.bottom - s.top - 1) > 1.5)
    errors.push('Aperture does not end at source lip');
  if (c.left < 0 || c.right > innerWidth || c.top < 0)
    errors.push('Card exceeds viewport');
  const nodes = document.createTreeWalker(
    card.querySelector('.slot-card-content')!,
    NodeFilter.SHOW_TEXT,
  );
  while (nodes.nextNode()) {
    const node = nodes.currentNode;
    if (!node.textContent?.trim()) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    for (const r of range.getClientRects()) {
      if (r.top < c.top || r.bottom > Math.min(c.bottom, a.bottom)) continue;
      const x = Math.max(r.left, Math.min(w.x + w.width / 2, r.right));
      const y = Math.max(r.top, Math.min(w.y + w.height / 2, r.bottom));
      if (
        Math.hypot(x - w.x - w.width / 2, y - w.y - w.height / 2) <
        w.width * 0.5 + 4
      )
        errors.push(`Text enters wheel clearance: ${node.textContent}`);
    }
  }
  for (const control of slot.querySelectorAll('a, button')) {
    const r = control.getBoundingClientRect();
    if (!r.width) continue;
    const hit = document.elementFromPoint(
      r.x + r.width / 2,
      r.y + r.height / 2,
    );
    if (!hit || !control.contains(hit))
      errors.push('Inserted card blocks a slot control');
  }
  return errors;
}
