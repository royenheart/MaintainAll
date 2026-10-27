/*
 * Browser-injected product-demo chrome for live captures.
 *
 * Usage:
 *   await page.evaluate(installProductDemoOverlay, {
 *     steps: [{ label: 'Initialize task', detail: 'New session' }, ...],
 *     theme: 'light',
 *     railWidth: 130,
 *     redactions: [String.raw`/home/[^/]+`, String.raw`\bsecret-[A-Za-z0-9-]+`],
 *   })
 *   await page.evaluate(() => window.__productDemo.setStep(2))
 *   await page.evaluate(() => window.__productDemo.caption('Saving the task'))
 *
 * The overlay is explanatory chrome, not evidence. It deliberately has no
 * decorative cursor and no free-floating frame. Keep the recorded interaction
 * real and log the evidence elsewhere.
 */
(() => {
  const STYLE = `
    [data-product-demo-rail] {
      position: fixed; inset: 0 auto 0 0; z-index: 2147483647;
      display: flex; flex-direction: column; box-sizing: border-box;
      width: var(--demo-rail-width, 130px); padding: 18px 12px 16px;
      font-family: ui-sans-serif, system-ui, sans-serif;
      background: var(--demo-rail-bg, #fbfcfe); color: var(--demo-ink, #1d2c41);
      border-right: 1px solid var(--demo-border, #e4eaf2);
      pointer-events: none; overflow: hidden;
    }
    [data-product-demo-rail] .demo-brand {
      font: 700 9px/12px ui-monospace, monospace; letter-spacing: .14em;
      color: var(--demo-muted, #718198);
    }
    [data-product-demo-rail] .demo-brand small {
      display: block; margin-top: 4px; font: 500 7px/10px ui-sans-serif, system-ui, sans-serif;
      letter-spacing: .02em; color: var(--demo-faint, #a5b2c3);
    }
    [data-product-demo-rail] .demo-live {
      align-self: flex-start; margin-top: 12px; padding: 4px 8px;
      border: 1px solid var(--demo-live-border, #bfe2ce); border-radius: 999px;
      background: var(--demo-live-bg, #eef9f2); color: var(--demo-live-ink, #1c6b4d);
      font: 700 7px/10px ui-sans-serif, system-ui, sans-serif; letter-spacing: .08em;
    }
    [data-product-demo-rail] .demo-steps {
      position: relative; flex: 1; margin-top: 18px; padding-left: 0;
    }
    [data-product-demo-rail] .demo-line,
    [data-product-demo-rail] .demo-fill {
      position: absolute; left: 18px; top: 14px; width: 1px;
      background: var(--demo-border, #e4eaf2);
    }
    [data-product-demo-rail] .demo-line { bottom: 18px; }
    [data-product-demo-rail] .demo-fill {
      width: 2px; background: var(--demo-accent, #4b7df0);
      transition: height .8s cubic-bezier(.2,.8,.2,1);
    }
    [data-product-demo-rail] .demo-step {
      position: relative; display: flex; align-items: flex-start; gap: 9px;
      min-height: 66px; padding: 8px 0 8px 0; opacity: .52;
    }
    [data-product-demo-rail] .demo-step.active { opacity: 1; }
    [data-product-demo-rail] .demo-step.done { opacity: 1; }
    [data-product-demo-rail] .demo-num {
      position: relative; z-index: 2; display: grid; place-items: center;
      width: 26px; height: 26px; flex: none; border-radius: 50%;
      border: 1px solid var(--demo-border, #d6e1ee); background: var(--demo-rail-bg, #fbfcfe);
      color: var(--demo-faint, #90a0b4); font: 700 9px/12px ui-monospace, monospace;
    }
    [data-product-demo-rail] .demo-step.done .demo-num {
      border-color: var(--demo-done, #1d7d57); background: var(--demo-done, #1d7d57); color: #fff;
    }
    [data-product-demo-rail] .demo-step.active .demo-num {
      border-color: var(--demo-accent, #4b7df0); background: var(--demo-accent, #4b7df0); color: #fff;
      box-shadow: 0 0 0 4px var(--demo-accent-soft, #4b7df01c);
    }
    [data-product-demo-rail] .demo-copy { min-width: 0; padding-top: 3px; }
    [data-product-demo-rail] .demo-label {
      display: block; color: var(--demo-muted, #8494a7);
      font: 700 8px/11px ui-sans-serif, system-ui, sans-serif;
      letter-spacing: .08em; text-transform: uppercase; white-space: nowrap;
    }
    [data-product-demo-rail] .demo-step.done .demo-label { color: var(--demo-done-ink, #46705e); }
    [data-product-demo-rail] .demo-step.active .demo-label { color: var(--demo-ink, #1d2c41); }
    [data-product-demo-rail] .demo-detail {
      display: none; margin-top: 2px; color: var(--demo-muted, #637892);
      font: 500 7px/10px ui-sans-serif, system-ui, sans-serif; white-space: nowrap;
    }
    [data-product-demo-rail] .demo-step.active .demo-detail { display: block; }
    [data-product-demo-rail] .demo-step.active .demo-copy {
      flex: 1; margin: -8px -8px -8px 0; padding: 8px 8px;
      border: 1px solid var(--demo-border, #dfe7f1); border-radius: 7px;
      background: var(--demo-card, #fff); box-shadow: 0 4px 16px #263b5510;
    }
    [data-product-demo-rail] .demo-foot {
      font: 700 13px/16px ui-monospace, monospace; color: var(--demo-ink, #334863);
    }
    [data-product-demo-rail] .demo-foot small {
      display: block; margin-top: 2px; font: 500 7px/10px ui-sans-serif, system-ui, sans-serif;
      color: var(--demo-faint, #9aa9bb);
    }
    [data-product-demo-caption] {
      position: fixed; left: calc(var(--demo-rail-width, 130px) + 14px); bottom: 16px;
      z-index: 2147483647; max-width: 70vw; padding: 7px 10px;
      border: 1px solid var(--demo-border, #d9e1ed); border-radius: 8px;
      background: var(--demo-caption-bg, #ffffffed); color: var(--demo-ink, #314158);
      font: 500 11px/15px ui-sans-serif, system-ui, sans-serif; pointer-events: none;
    }
    [data-product-demo-focus] {
      position: fixed; z-index: 2147483646; border: 2px solid var(--demo-accent, #6ea8ff);
      border-radius: 9px; box-shadow: 0 0 0 5px var(--demo-accent-soft, #6ea8ff20);
      opacity: 0; pointer-events: none; transition: opacity .15s;
    }
  `;

  function slug(index) {
    return String(index + 1).padStart(2, '0');
  }

  function cleanText(value, redactions) {
    let text = String(value);
    for (const pattern of redactions) {
      text = text.replace(new RegExp(pattern, 'g'), '[redacted]');
    }
    return text;
  }

  window.installProductDemoOverlay = (config = {}) => {
    if (window.__productDemo) return window.__productDemo;
    const steps = Array.isArray(config.steps) ? config.steps : [];
    if (steps.length === 0) throw new Error('installProductDemoOverlay requires steps');
    const theme = config.theme === 'dark' ? 'dark' : 'light';
    const css = document.createElement('style');
    css.textContent = STYLE;
    document.documentElement.appendChild(css);
    const vars = document.documentElement.style;
    vars.setProperty('--demo-rail-width', `${config.railWidth || 130}px`);
    if (theme === 'dark') {
      vars.setProperty('--demo-rail-bg', '#10151e');
      vars.setProperty('--demo-ink', '#e8eef8');
      vars.setProperty('--demo-muted', '#8f9caf');
      vars.setProperty('--demo-faint', '#6f7d91');
      vars.setProperty('--demo-border', '#273244');
      vars.setProperty('--demo-card', '#1a2330');
      vars.setProperty('--demo-caption-bg', '#0d131ce8');
      vars.setProperty('--demo-live-bg', '#0f241c');
      vars.setProperty('--demo-live-ink', '#8fe0b3');
      vars.setProperty('--demo-live-border', '#2b654c');
      vars.setProperty('--demo-done-ink', '#8fe0b3');
    }
    const rail = document.createElement('div');
    rail.setAttribute('data-product-demo-rail', '');
    rail.innerHTML = `<div class="demo-brand">FLOW<small>${cleanText(config.subtitle || 'Product walkthrough', [])}</small></div>` +
      `<div class="demo-live">LIVE RUN</div>` +
      `<div class="demo-steps"><div class="demo-line"></div><div class="demo-fill"></div>${steps.map((step, index) =>
        `<div class="demo-step" data-demo-index="${index}"><div class="demo-num">${slug(index)}</div>` +
        `<div class="demo-copy"><span class="demo-label">${cleanText(step.label, [])}</span>` +
        `<span class="demo-detail">${cleanText(step.detail || '', [])}</span></div></div>`).join('')}</div>` +
      `<div class="demo-foot"><span data-demo-foot-count>01 / ${String(steps.length).padStart(2, '0')}</span>` +
      `<small data-demo-foot-label>${cleanText(steps[0].label, [])}</small></div>`;
    document.documentElement.appendChild(rail);
    const caption = document.createElement('div');
    caption.setAttribute('data-product-demo-caption', '');
    document.documentElement.appendChild(caption);
    const focus = document.createElement('div');
    focus.setAttribute('data-product-demo-focus', '');
    document.documentElement.appendChild(focus);
    const redactions = Array.isArray(config.redactions) ? config.redactions : [];
    const sanitize = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (const node of nodes) {
        if (!node.textContent) continue;
        const next = cleanText(node.textContent, redactions);
        if (next !== node.textContent) node.textContent = next;
      }
      for (const el of document.querySelectorAll('[data-changed-files]')) el.style.display = 'none';
    };
    let observer = null;
    if (config.sanitize !== false && redactions.length) {
      observer = new MutationObserver(sanitize);
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true });
      sanitize();
    }
    const setStep = index => {
      const bounded = Math.max(0, Math.min(steps.length - 1, index));
      for (const el of rail.querySelectorAll('.demo-step')) {
        const i = Number(el.getAttribute('data-demo-index'));
        el.classList.toggle('active', i === bounded);
        el.classList.toggle('done', i < bounded);
      }
      const stepHeight = 74;
      rail.querySelector('.demo-fill').style.height = `${bounded * stepHeight}px`;
      rail.querySelector('[data-demo-foot-count]').textContent = `${slug(bounded)} / ${String(steps.length).padStart(2, '0')}`;
      rail.querySelector('[data-demo-foot-label]').textContent = steps[bounded].label;
    };
    const setCaption = text => { caption.textContent = text; };
    const flash = rect => {
      if (!rect) return;
      focus.style.left = `${rect.x - 5}px`;
      focus.style.top = `${rect.y - 5}px`;
      focus.style.width = `${rect.width + 10}px`;
      focus.style.height = `${rect.height + 10}px`;
      focus.style.opacity = '1';
      setTimeout(() => { focus.style.opacity = '0'; }, 650);
    };
    const api = { setStep, caption: setCaption, focus: flash, sanitize, destroy() {
      if (observer) observer.disconnect();
      rail.remove(); caption.remove(); focus.remove(); delete window.__productDemo;
    } };
    window.__productDemo = api;
    setStep(0);
    return api;
  };
})();
