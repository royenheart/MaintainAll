// This function is serialized into the browser; keep it free of external dependencies.
export function inspectConceptLayout() {
  const issues: string[] = [];
  const tolerance = 1.5;
  const root = document.querySelector<HTMLElement>('.design-concept');
  if (!root) return ['Missing design concept'];
  const rect = (element: Element) => element.getBoundingClientRect();
  const visible = (element: Element) =>
    rect(element).width > 0 && rect(element).height > 0;
  const contains = (parent: Element, child: Element, label: string) => {
    const p = rect(parent),
      c = rect(child);
    if (
      c.left < p.left - tolerance ||
      c.right > p.right + tolerance ||
      c.top < p.top - tolerance ||
      c.bottom > p.bottom + tolerance
    )
      issues.push(`${label} escapes its container`);
  };
  const collision = (a: Element, b: Element, label: string) => {
    const x = rect(a),
      y = rect(b);
    if (
      Math.min(x.right, y.right) - Math.max(x.left, y.left) > tolerance &&
      Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > tolerance
    )
      issues.push(`${label} overlaps`);
  };
  const region = (name: string) =>
    root.querySelector<HTMLElement>(`[data-concept-region='${name}']`)!;
  const nav = region('navigation'),
    scene = region('scene'),
    footer = region('footer');
  const music = region('music'),
    legal = region('legal');
  for (const element of [nav, scene, footer])
    contains(root, element, element.dataset.conceptRegion!);
  collision(nav, scene, 'Navigation and scene');
  collision(scene, footer, 'Scene and footer');
  collision(music, legal, 'Music and registration links');
  contains(footer, music, 'Music');
  contains(footer, legal, 'Registration links');
  if (Math.abs(rect(scene).bottom - rect(footer).top) > tolerance)
    issues.push('Scene and footer edges differ');
  if (
    window.innerWidth > 720 &&
    Math.abs(rect(scene).left - rect(nav).right) > tolerance
  )
    issues.push('Sidebar and scene edges differ');
  if (
    window.innerWidth <= 720 &&
    Math.abs(rect(scene).top - rect(nav).bottom) > tolerance
  )
    issues.push('Top navigation and scene edges differ');
  const player = root.querySelector<HTMLElement>('.unified-player')!;
  const children = Array.from(player.children).filter(visible);
  children.forEach((child) => contains(player, child, child.className));
  children.forEach((child, index) =>
    children
      .slice(index + 1)
      .forEach((other) =>
        collision(child, other, `${child.className} and ${other.className}`),
      ),
  );
  for (const control of root.querySelectorAll('button, input, nav a')) {
    if (!visible(control)) continue;
    const owner =
      control.closest('.unified-player') ??
      control.closest('.concept-viewport') ??
      nav;
    contains(
      owner,
      control,
      control.getAttribute('aria-label') ?? control.textContent ?? 'Control',
    );
  }
  for (const child of nav.children)
    if (visible(child)) contains(nav, child, `Navigation ${child.className}`);
  const viewport = root.querySelector('.concept-viewport')!;
  const canvas = root.querySelector('canvas');
  if (canvas) {
    const parent = rect(root.querySelector('.scene-experience')!);
    const c = rect(canvas);
    if (
      Math.abs(c.width - parent.width) > tolerance ||
      Math.abs(c.height - parent.height) > tolerance
    )
      issues.push('Canvas CSS size differs from scene');
    contains(viewport, canvas, 'Scene canvas');
  }
  if (document.documentElement.scrollWidth > window.innerWidth + tolerance)
    issues.push('Document overflows horizontally');
  return issues;
}
