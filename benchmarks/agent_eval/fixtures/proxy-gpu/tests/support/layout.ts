export interface LayoutReport {
  issues: string[];
  boxes: Record<
    string,
    {
      x: number;
      y: number;
      width: number;
      height: number;
      right: number;
      bottom: number;
    }
  >;
}

// Keep this function self-contained: Playwright serializes it into the browser.
export function inspectLayout(
  scope?: Document | HTMLElement | void,
): LayoutReport {
  const root = scope ?? document;
  const issues: string[] = [];
  const boxes: LayoutReport['boxes'] = {};
  const doc = root instanceof Document ? root : root.ownerDocument;
  const rect = (selector: string, name: string) => {
    const element = root.querySelector(selector);
    if (!element) {
      issues.push(`Missing ${name}`);
      return null;
    }
    const r = element.getBoundingClientRect();
    const box = {
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      right: r.right,
      bottom: r.bottom,
    };
    boxes[name] = box;
    if (r.width <= 0 || r.height <= 0)
      issues.push(`${name} has no visible area`);
    return box;
  };
  type Box = NonNullable<ReturnType<typeof rect>>;
  const contains = (outer: Box, inner: Box, name: string) => {
    if (
      inner.x < outer.x - 1.5 ||
      inner.y < outer.y - 1.5 ||
      inner.right > outer.right + 1.5 ||
      inner.bottom > outer.bottom + 1.5
    )
      issues.push(`${name} escapes its container`);
  };
  const separate = (a: Box, b: Box, name: string) => {
    if (
      Math.min(a.right, b.right) - Math.max(a.x, b.x) > 1.5 &&
      Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y) > 1.5
    )
      issues.push(`${name} overlap`);
  };
  const frame = rect('.home-frame', 'frame');
  const nav = rect('[data-layout="navigation"]', 'navigation');
  const scene = rect('[data-layout="scene"]', 'scene');
  const footer = rect('[data-layout="footer"]', 'footer');
  const music = rect('[data-layout="music"]', 'music');
  const legal = rect('[data-layout="legal"]', 'legal');
  const toolbar = rect('.scene-toolbar', 'toolbar');
  if (frame && nav && scene && footer && music && legal && toolbar) {
    [nav, scene, footer].forEach((box, i) =>
      contains(frame, box, ['Navigation', 'Scene', 'Footer'][i]!),
    );
    contains(footer, music, 'Music');
    contains(footer, legal, 'Legal links');
    contains(scene, toolbar, 'Scene controls');
    separate(nav, scene, 'Navigation and scene');
    separate(scene, footer, 'Scene and footer');
    separate(music, legal, 'Music and legal links');
    if (Math.abs(scene.bottom - footer.y) > 1.5)
      issues.push('Scene and footer are misaligned');
    if (doc.defaultView!.innerWidth <= 720) {
      if (Math.abs(scene.y - nav.bottom) > 1.5)
        issues.push('Mobile navigation and scene are misaligned');
    } else if (Math.abs(scene.x - nav.right) > 1.5)
      issues.push('Desktop navigation and scene are misaligned');
    const canvas = root.querySelector('canvas');
    if (canvas) {
      const r = canvas.getBoundingClientRect();
      if (
        Math.abs(r.width - scene.width) > 1.5 ||
        Math.abs(r.height - scene.height) > 1.5
      )
        issues.push('Canvas does not fill its scene');
    }
    for (const element of root.querySelectorAll(
      '.scene-control, .music-toggle, .profile-nav a',
    )) {
      const r = element.getBoundingClientRect();
      if (r.height < 43) issues.push('Interactive target is too short');
    }
  }
  if (doc.documentElement.scrollWidth > doc.documentElement.clientWidth + 1)
    issues.push('Document overflows horizontally');
  return { issues, boxes };
}
