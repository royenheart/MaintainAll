import { useEffect, useId, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence } from 'motion/react';
import { SlotPreviewCard, type CardPlacement } from './SlotPreviewCard';
import { site } from '../../lib/content/load';
import type { SceneId, SiteContent } from '../../lib/content/schema';
import { DockIcon } from './DockIcon';
import { ElsewhereMark } from './ElsewhereMark';
import { cardWindow, stepBoundCard } from './bound-card-sequence';
import type {
  ElsewhereStudy,
  CardExtraction,
  CardMaterial,
  CardArtStudy,
  ElsewhereMark as MarkStudy,
} from './card-finishes';

/** Components select bound cards; the card's native action opens its destination. */
export function ElsewhereSegments({
  study = 'tile',
  extraction = 'slide',
  material = 'drift',
  scene = 'cubes',
  art = scene === 'horizon' ? 'relief' : 'foil',
  mark = 'editorial',
  reduced = false,
  links = site.links,
}: {
  study?: ElsewhereStudy;
  extraction?: CardExtraction;
  material?: CardMaterial;
  art?: CardArtStudy;
  scene?: SceneId;
  mark?: MarkStudy;
  reduced?: boolean;
  links?: SiteContent['links'];
}) {
  const host = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastWheel = useRef(0);
  const gesture = useRef<{ x: number; y: number } | null>(null);
  const pinned = useRef(false);
  const id = useId();
  const cards = links.filter((link) => link.preview);
  const [active, setActive] = useState<number | null>(null);
  const [selected, setSelected] = useState(0);
  const [browsing, setBrowsing] = useState(false);
  const [shown, setShown] = useState<number | null>(null);
  const [leaving, setLeaving] = useState(false);
  const requested = useRef<number | null>(null);
  // A key cannot re-enter while its old face is still returning. Coalesce rapid
  // input into the latest request, then change the physical face after exit.
  useEffect(() => {
    requested.current = active;
    if (leaving) return;
    if (shown === null) {
      if (active !== null) setShown(active);
    } else if (active !== shown) setLeaving(true);
  }, [active, shown, leaving]);
  const [position, setPosition] = useState<CardPlacement>({
    left: 0,
    width: 280,
    bottom: 0,
    lip: 0,
    maxHeight: 0,
    lowerWidth: 0,
    exposed: 4,
    storedOpacity: 0.2,
  });
  const cancel = () => clearTimeout(timer.current);
  const leave = () => {
    cancel();
    timer.current = setTimeout(() => {
      if (
        !pinned.current &&
        !host.current?.querySelector(':focus-visible') &&
        !host.current?.matches(':hover') &&
        !panel.current?.matches(':focus-within') &&
        !panel.current?.querySelector('.elsewhere-preview:hover')
      )
        setActive(null);
    }, 180);
  };
  const reveal = (index: number, pin = false) => {
    cancel();
    const owner = host.current;
    if (
      !owner ||
      !cards[index] ||
      owner.closest('[inert]') ||
      owner.closest('.rotary-deck')?.getAttribute('data-moving') === 'true'
    )
      return;
    const slot = owner.closest('.rotary-card')!.getBoundingClientRect();
    const wheel = owner
      .closest('.orbit-study')
      ?.querySelector('.orbit-wheel')
      ?.getBoundingClientRect();
    const stack = owner.querySelector<HTMLElement>('.slot-card-stack')!;
    const mouth = stack.getBoundingClientRect();
    const stock = getComputedStyle(stack);
    const width = Math.min(mouth.width, innerWidth - 48);
    const left = Math.max(12, Math.min(mouth.left, innerWidth - width - 36));
    setPosition({
      width,
      lip: innerHeight - slot.top - 1,
      bottom: innerHeight - slot.top - 8,
      maxHeight: Math.max(64, slot.top - 40),
      left,
      lowerWidth: Math.max(68, (wheel?.left ?? slot.right) - left - 28),
      exposed: parseFloat(stock.getPropertyValue('--stored-peek')),
      storedOpacity: parseFloat(stock.opacity),
    });
    pinned.current ||= pin;
    if (active !== index) setBrowsing(active !== null);
    setSelected(index);
    setActive(index);
  };
  const step = (delta: number) =>
    reveal(stepBoundCard(active ?? selected, delta, cards.length), true);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (active === null) return;
    const dismiss = () => {
      clearTimeout(timer.current);
      pinned.current = false;
      setActive(null);
    };
    const outside = (event: PointerEvent) => {
      if (
        !host.current?.contains(event.target as Node) &&
        !panel.current?.contains(event.target as Node)
      )
        dismiss();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      event.preventDefault();
      if (panel.current?.contains(document.activeElement))
        host.current
          ?.querySelector<HTMLElement>(`[data-binding-index="${active}"]`)
          ?.focus();
      dismiss();
    };
    const crossGap = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || pinned.current) return;
      const anchor = host.current?.getBoundingClientRect();
      const preview = panel.current?.querySelector(
        '.slot-card-aperture[data-present="true"] .elsewhere-preview',
      );
      if (!anchor || !preview) return;
      const p = preview.getBoundingClientRect();
      const bridge =
        event.clientY >= p.bottom - 8 &&
        event.clientY <= anchor.bottom &&
        event.clientX >= Math.min(p.left, anchor.left) &&
        event.clientX <= Math.max(p.right, anchor.right);
      if (
        bridge ||
        panel.current?.contains(event.target as Node) ||
        host.current?.contains(event.target as Node)
      )
        clearTimeout(timer.current);
      else if (
        !host.current?.querySelector(':focus-visible') &&
        !panel.current?.matches(':focus-within')
      ) {
        clearTimeout(timer.current);
        timer.current = setTimeout(dismiss, 180);
      }
    };
    const deck = host.current?.closest('.rotary-deck');
    const dock = host.current?.closest('.orbit-dock');
    const observer = new MutationObserver(() => {
      if (
        deck?.getAttribute('data-moving') === 'true' ||
        host.current?.closest('[inert]')
      )
        dismiss();
    });
    if (deck)
      observer.observe(deck, {
        attributes: true,
        subtree: true,
        attributeFilter: ['data-moving', 'inert'],
      });
    // A scene transition inerts the whole dock, not the deck. The portal lives
    // under the study root, outside that dock, so observe its inert boundary too.
    if (dock)
      observer.observe(dock, {
        attributes: true,
        attributeFilter: ['inert'],
      });
    window.addEventListener('resize', dismiss);
    document.addEventListener('pointerdown', outside);
    document.addEventListener('pointermove', crossGap, { passive: true });
    document.addEventListener('keydown', escape, true);
    document.addEventListener('visibilitychange', dismiss);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', dismiss);
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('pointermove', crossGap);
      document.removeEventListener('keydown', escape, true);
      document.removeEventListener('visibilitychange', dismiss);
    };
  }, [active]);
  const link = active === null ? null : cards[active];
  const shownLink = shown === null ? null : cards[shown];
  const root = host.current?.closest('.orbit-study');
  const visibleCards = cardWindow(shown ?? active ?? selected, cards.length);
  const wheel = (delta: number) => {
    if (Math.abs(delta) < 12 || performance.now() - lastWheel.current < 300)
      return;
    lastWheel.current = performance.now();
    step(delta);
  };
  return (
    <div
      ref={host}
      className="orbit-ribbon-copy orbit-elsewhere orbit-segments"
      data-selected-card={selected}
    >
      {!!cards.length && (
        <div
          className="slot-card-stack"
          data-study={study}
          aria-hidden="true"
          onWheel={(event) => {
            event.stopPropagation();
            wheel(event.deltaY);
          }}
        >
          {visibleCards
            .filter((index) => index !== shown)
            .slice()
            .reverse()
            .map((index) => {
              const depth = visibleCards.indexOf(index);
              return (
                <i
                  className="slot-card-face"
                  key={cards[index]!.href}
                  data-card-binding={cards[index]!.href}
                  data-depth={depth}
                  style={
                    {
                      '--card-depth': depth,
                      zIndex: 3 - depth,
                    } as CSSProperties
                  }
                />
              );
            })}
        </div>
      )}
      <nav aria-label="Elsewhere" tabIndex={-1}>
        {links.map((item) => {
          const index = cards.findIndex((card) => card.href === item.href);
          const content = (
            <>
              <span className="orbit-segment-paint" aria-hidden="true" />
              <span className="orbit-segment-label" aria-hidden="true">
                {study === 'tile' && (
                  <ElsewhereMark
                    kind={item.label === 'GitHub' ? 'github' : 'blog'}
                    study={mark}
                  />
                )}
                {study !== 'tile' && (
                  <DockIcon
                    name={item.label === 'GitHub' ? 'repository' : 'journal'}
                  />
                )}
                {study === 'index' && (
                  <span className="elsewhere-ticks">
                    <i />
                    <i />
                    <i />
                  </span>
                )}
              </span>
            </>
          );
          return index < 0 ? (
            <a
              key={item.href}
              className="orbit-segment-link"
              href={item.href}
              aria-label={item.label}
            >
              {content}
            </a>
          ) : (
            <button
              key={item.href}
              type="button"
              className="orbit-segment-link"
              aria-label={item.label}
              aria-controls={id}
              aria-expanded={active === index}
              data-binding-index={index}
              data-preview-open={active === index}
              data-card-binding={item.href}
              onPointerEnter={(event) => {
                if (event.pointerType !== 'touch') reveal(index);
              }}
              onPointerLeave={(event) => {
                if (event.pointerType !== 'touch') leave();
              }}
              onFocus={(event) => {
                if (event.currentTarget.matches(':focus-visible'))
                  reveal(index);
              }}
              onBlur={leave}
              onClick={() => reveal(index, true)}
              onKeyDown={(event) => {
                if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                  event.preventDefault();
                  event.stopPropagation();
                  step(event.key === 'ArrowRight' ? 1 : -1);
                  panel.current?.focus();
                }
              }}
            >
              {content}
            </button>
          );
        })}
      </nav>
      {root &&
        createPortal(
          <div
            ref={panel}
            id={id}
            className="slot-card-portals"
            role="region"
            aria-label="Elsewhere cards"
            aria-roledescription="card carousel"
            aria-hidden={active === null}
            tabIndex={active === null ? -1 : 0}
            data-card-index={active ?? selected}
            data-card-count={cards.length}
            onPointerEnter={cancel}
            onPointerLeave={leave}
            onBlur={leave}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault();
                step(event.key === 'ArrowRight' ? 1 : -1);
                panel.current?.focus();
              }
            }}
            onWheel={(event) => {
              event.stopPropagation();
              const card = panel.current?.querySelector<HTMLElement>(
                '.slot-card-aperture[data-present="true"] .elsewhere-preview',
              );
              if (
                card &&
                card.scrollHeight > card.clientHeight + 1 &&
                ((event.deltaY > 0 &&
                  card.scrollTop + card.clientHeight < card.scrollHeight - 1) ||
                  (event.deltaY < 0 && card.scrollTop > 0))
              )
                return;
              wheel(event.deltaY);
            }}
            onPointerDown={(event) => {
              event.stopPropagation();
              if (event.pointerType === 'touch')
                gesture.current = { x: event.clientX, y: event.clientY };
            }}
            onPointerUp={(event) => {
              event.stopPropagation();
              const start = gesture.current;
              gesture.current = null;
              if (
                start &&
                Math.abs(event.clientX - start.x) > 40 &&
                Math.abs(event.clientX - start.x) >
                  Math.abs(event.clientY - start.y)
              )
                step(start.x - event.clientX);
            }}
            onPointerCancel={() => {
              gesture.current = null;
            }}
          >
            <AnimatePresence
              custom={active !== null}
              onExitComplete={() => {
                setShown(requested.current);
                setLeaving(false);
              }}
            >
              {!leaving && shownLink?.preview && (
                <SlotPreviewCard
                  key={shownLink.href}
                  link={shownLink}
                  id={`${id}-current`}
                  study={study}
                  extraction={extraction}
                  material={material}
                  art={art}
                  scene={scene}
                  placement={position}
                  reduced={reduced}
                  browsing={browsing}
                  index={shown!}
                />
              )}
            </AnimatePresence>
            <span className="sr-only" aria-live="polite">
              {link
                ? `${link.label}. Card ${active! + 1} of ${cards.length}. Scroll or use left and right arrow keys to browse cards.`
                : ''}
            </span>
          </div>,
          root,
        )}
    </div>
  );
}
