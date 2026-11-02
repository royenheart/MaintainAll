import { useRef, type ReactNode } from 'react';
import { AnimatePresence, motion, useIsPresent } from 'motion/react';
import { cardIndex } from './sequence';

export interface OrbitCard {
  id: string;
  label: string;
  content: ReactNode;
  /** IDs of cards bound to interactive components inside this slot. */
  boundCards?: readonly string[];
}
function FrontCard({
  card,
  direction,
  reduced,
}: {
  card: OrbitCard;
  direction: number;
  reduced: boolean;
}) {
  const present = useIsPresent();
  return (
    <motion.article
      className="orbit-card orbit-card-front"
      aria-hidden={!present}
      inert={!present}
      aria-label={card.label}
      initial={
        reduced
          ? false
          : { y: `${direction * 35}%`, rotateX: -direction * 24, opacity: 0 }
      }
      animate={{ y: 0, rotateX: 0, opacity: 1 }}
      exit={{
        y: reduced ? 0 : `${-direction * 35}%`,
        rotateX: reduced ? 0 : direction * 24,
        opacity: 0,
      }}
      transition={{ duration: reduced ? 0 : 0.26, ease: [0.22, 1, 0.36, 1] }}
    >
      {card.content}
    </motion.article>
  );
}

export function CardDeck({
  cards,
  index,
  onIndex,
  reduced,
  onClose,
}: {
  cards: OrbitCard[];
  index: number;
  onIndex(index: number): void;
  reduced: boolean;
  onClose(): void;
}) {
  const lastWheel = useRef(0);
  const pointer = useRef<number | null>(null);
  const direction = useRef(1);
  const step = (delta: number) => {
    direction.current = Math.sign(delta);
    onIndex(cardIndex(index, delta, cards.length));
  };
  const card = cards[index]!;
  const next = cards[index + 1];
  return (
    <section
      className="orbit-deck"
      id="orbit-deck"
      data-card-count={cards.length}
      aria-label="Information cards"
      onWheel={(event) => {
        if (
          Math.abs(event.deltaY) < 12 ||
          performance.now() - lastWheel.current < 450
        )
          return;
        lastWheel.current = performance.now();
        step(event.deltaY);
      }}
      onPointerDown={(event) => {
        if (event.pointerType !== 'mouse') pointer.current = event.clientY;
      }}
      onPointerUp={(event) => {
        if (
          pointer.current !== null &&
          Math.abs(event.clientY - pointer.current) > 35
        )
          step(pointer.current - event.clientY);
        pointer.current = null;
      }}
      onPointerCancel={() => {
        pointer.current = null;
      }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          event.preventDefault();
          step(event.key === 'ArrowDown' ? 1 : -1);
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <div className="orbit-deck-stack">
        {next && (
          <div className="orbit-card orbit-card-back" aria-hidden="true">
            <span>
              {String(index + 2).padStart(2, '0')} / {next.label}
            </span>
          </div>
        )}
        <AnimatePresence mode="wait" initial={false}>
          <FrontCard
            key={card.id}
            card={card}
            direction={direction.current}
            reduced={reduced}
          />
        </AnimatePresence>
      </div>
      <nav className="orbit-card-navigation" aria-label="Card navigation">
        <span aria-live="polite">
          {String(index + 1).padStart(2, '0')}{' '}
          <span>/ {String(cards.length).padStart(2, '0')}</span>
        </span>
        <button
          aria-label="Previous card"
          disabled={index === 0}
          onClick={() => step(-1)}
        >
          ↑
        </button>
        <button
          aria-label="Next card"
          disabled={index === cards.length - 1}
          onClick={() => step(1)}
        >
          ↓
        </button>
        <button aria-label="Close information cards" onClick={onClose}>
          ×
        </button>
      </nav>
    </section>
  );
}
