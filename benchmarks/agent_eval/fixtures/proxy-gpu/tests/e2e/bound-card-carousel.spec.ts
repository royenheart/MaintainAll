import { expect, test } from '@playwright/test';

for (const count of [2, 8])
  test(`${count} bound cards use a three-card diagonal window with isolated navigation`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    await page.goto(
      `/preview/?card=elsewhere&graphics=poster&skipIntro=1${count === 8 ? '&cards=demo' : ''}`,
    );
    await expect(page.locator('.slot-card-stack i')).toHaveCount(
      Math.min(3, count),
    );
    const edges = await page
      .locator('.slot-card-stack i')
      .evaluateAll((nodes) =>
        nodes
          .map((n) => ({
            depth: Number((n as HTMLElement).dataset.depth),
            rect: n.getBoundingClientRect().toJSON(),
          }))
          .sort((a, b) => a.depth - b.depth),
      );
    for (let i = 1; i < edges.length; i++) {
      expect(edges[i]!.rect.left).toBeGreaterThan(edges[i - 1]!.rect.left);
      expect(edges[i]!.rect.top).toBeLessThan(edges[i - 1]!.rect.top);
      expect(edges[i]!.rect.width).toBeCloseTo(edges[0]!.rect.width, 1);
      expect(edges[i - 1]!.rect.top - edges[i]!.rect.top).toBeCloseTo(3, 1);
    }
    const first = page.getByRole('button', {
      name: count === 8 ? 'Sample 1' : 'Blog',
      exact: true,
    });
    await first.click();
    const deck = page.getByRole('region', { name: 'Elsewhere cards' }),
      card = page.getByRole('group', { name: 'Current card' });
    await expect(card).toHaveAttribute('data-state', 'open');
    await expect(page.locator('.slot-card-stack i')).toHaveCount(
      Math.min(3, count) - 1,
    );
    await expect(page.locator('.slot-card-rear')).toHaveCount(0);
    const edge = page.locator('.slot-card-stack i').first();
    const radius = await edge.evaluate(
      (el) => getComputedStyle(el).borderTopLeftRadius,
    );
    await expect(card).toHaveCSS('border-top-left-radius', radius);
    expect((await card.boundingBox())!.width).toBeCloseTo(
      edges[0]!.rect.width,
      1,
    );
    expect((await card.boundingBox())!.x).toBeCloseTo(edges[0]!.rect.left, 1);
    await expect(page.locator('.slot-card-stack')).toHaveCSS('opacity', '0.2');
    const parked = await page
      .locator('.slot-card-stack i')
      .evaluateAll((nodes) => {
        const top = document
          .querySelector('.rotary-card-active')!
          .getBoundingClientRect().top;
        return nodes.map((n) => top - n.getBoundingClientRect().top);
      });
    for (const height of parked) {
      expect(height).toBeGreaterThanOrEqual(4);
      expect(height).toBeLessThanOrEqual(10);
    }
    await page.evaluate(() => {
      (window as unknown as { maxCards: number }).maxCards = 0;
      new MutationObserver(() => {
        const w = window as unknown as { maxCards: number };
        w.maxCards = Math.max(
          w.maxCards,
          document.querySelectorAll(
            '.slot-card-portals .elsewhere-preview, .slot-card-stack i',
          ).length,
        );
      }).observe(document.querySelector('.orbit-study')!, {
        childList: true,
        subtree: true,
      });
    });
    await card.hover();
    await page.mouse.wheel(0, 100);
    await expect(deck).toHaveAttribute('data-card-index', '1');
    await expect(card).toHaveAttribute('data-state', 'open');
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-card-index',
      '2',
    );
    await deck.focus();
    for (let i = 0; i < count + 2; i++) await page.keyboard.press('ArrowRight');
    await expect(deck).toHaveAttribute('data-card-index', String(3 % count));
    await expect(card).toHaveAttribute('data-state', 'open');
    expect(
      await page.evaluate(
        () => (window as unknown as { maxCards: number }).maxCards,
      ),
    ).toBeLessThanOrEqual(3);
    const target = page.getByRole('button', {
      name: count === 8 ? 'Sample 7' : 'Blog',
      exact: true,
    });
    await target.click();
    await expect(deck).toHaveAttribute(
      'data-card-index',
      count === 8 ? '6' : '0',
    );
    await expect(card).toContainText(count === 8 ? 'Sample 7' : 'Blog');
    await expect(card).toHaveAttribute('data-state', 'open');
    await deck.focus();
    await page.keyboard.press('ArrowLeft');
    await expect(deck).toHaveAttribute(
      'data-card-index',
      count === 8 ? '5' : '1',
    );
    await page.keyboard.press('Escape');
    await expect(page.locator('.slot-card-aperture')).toHaveCount(0);
    await expect(page.locator('.slot-card-stack')).toHaveCSS(
      'visibility',
      'visible',
    );
    await expect(page.locator('.slot-card-stack i')).toHaveCount(
      Math.min(3, count),
    );
    await expect(
      page.getByRole('button', {
        name: count === 8 ? 'Sample 6' : 'GitHub',
        exact: true,
      }),
    ).toBeFocused();
  });

test('horizontal touch swipe browses inner cards while the source slot stays selected', async ({
  browser,
}) => {
  const context = await browser.newContext({
      hasTouch: true,
      viewport: { width: 390, height: 844 },
    }),
    page = await context.newPage();
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto(
    '/preview/?card=elsewhere&cards=demo&graphics=poster&skipIntro=1',
  );
  await page.getByRole('button', { name: 'Sample 1', exact: true }).tap();
  const card = page.getByRole('group', { name: 'Current card' });
  await expect(card).toHaveAttribute('data-state', 'open');
  await card.dispatchEvent('pointerdown', {
    pointerType: 'touch',
    clientX: 200,
    clientY: 200,
  });
  await card.dispatchEvent('pointerup', {
    pointerType: 'touch',
    clientX: 100,
    clientY: 205,
  });
  await expect(
    page.getByRole('region', { name: 'Elsewhere cards' }),
  ).toHaveAttribute('data-card-index', '1');
  await expect(page.locator('.rotary-deck')).toHaveAttribute(
    'data-card-index',
    '2',
  );
  await context.close();
});

test('rapid cycles never resurrect an exiting key or leave the selected face empty', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto(
    '/preview/?card=elsewhere&cards=demo&graphics=poster&skipIntro=1',
  );
  await page.getByRole('button', { name: 'Sample 1', exact: true }).click();
  const deck = page.getByRole('region', { name: 'Elsewhere cards' });
  const card = page.getByRole('group', { name: 'Current card' });
  await expect(card).toHaveAttribute('data-state', 'open');
  for (let cycle = 0; cycle < 6; cycle++) {
    await deck.focus();
    for (let i = 0; i < 11; i++) await page.keyboard.press('ArrowRight');
    const index = Number(await deck.getAttribute('data-card-index'));
    await expect(card).toContainText(`Sample ${index + 1}`);
    await expect(card).toHaveAttribute('data-state', 'open');
    await expect(page.locator('.slot-card-aperture')).toHaveCount(1);
  }
  await deck.focus();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Sample 8', exact: true }).click();
  await expect(card).toContainText('Sample 8');
  await expect(card).toHaveAttribute('data-state', 'open');
});
