import { useState } from 'react';
import { motion, useIsPresent } from 'motion/react';
import { site } from '../../lib/content/load';
import { DockIcon } from './DockIcon';
import { SceneCardArt } from './SceneCardArt';
import type { SceneId } from '../../lib/content/schema';
import type {
  CardExtraction,
  CardMaterial,
  ElsewhereStudy,
  CardArtStudy,
} from './card-finishes';

export interface CardPlacement {
  left: number;
  width: number;
  bottom: number;
  lip: number;
  maxHeight: number;
  lowerWidth: number;
  exposed: number;
  storedOpacity: number;
}

/** The fixed aperture ends at the source slot's lip, occluding extraction. */
export function SlotPreviewCard({
  link,
  id,
  study,
  extraction,
  material,
  art,
  scene,
  placement,
  reduced,
  browsing,
  index,
}: {
  link: (typeof site.links)[number];
  id: string;
  study: ElsewhereStudy;
  extraction: CardExtraction;
  material: CardMaterial;
  art: CardArtStudy;
  scene: SceneId;
  placement: CardPlacement;
  reduced: boolean;
  browsing: boolean;
  index: number;
}) {
  const present = useIsPresent();
  const [settled, setSettled] = useState(false);
  const gap = placement.bottom - placement.lip;
  const side = index % 2 ? 1 : -1;
  const rotation =
    extraction === 'lift' ? -4 : extraction === 'fan' ? side * 3 : 0;
  const offset = extraction === 'fan' ? side * 16 : 0;
  // The returning face meets the same shallow, translucent edge at the mouth.
  const closed = `translate(0px, calc(100% - ${placement.exposed + 1 - gap}px)) rotate(0deg)`;
  const lifted = `translate(${offset}px, calc(45% - 7px)) rotate(${rotation}deg)`;
  const open = 'translate(0px, 0px) rotate(0deg)';
  const duration = extraction === 'lift' ? 0.34 : 0.28;
  return (
    <div
      className="slot-card-aperture"
      data-present={present}
      data-extraction={extraction}
      style={{
        left: placement.left - 12,
        width: placement.width + 24,
        bottom: placement.lip,
      }}
    >
      <motion.div
        id={present ? id : undefined}
        role={present ? 'group' : undefined}
        aria-label={present ? 'Current card' : undefined}
        aria-hidden={!present}
        inert={!present}
        className="elsewhere-preview slot-card-face"
        data-study={study}
        data-material={material}
        data-state={present ? (settled ? 'open' : 'entering') : 'returning'}
        data-card-binding={link.href}
        style={{ bottom: gap, maxHeight: placement.maxHeight }}
        initial={{
          transform: reduced ? open : closed,
          opacity: reduced ? 0 : placement.storedOpacity,
        }}
        animate={{
          transform:
            reduced || extraction === 'slide' ? open : [null, lifted, open],
          opacity: 1,
          transition: {
            duration: reduced ? 0.06 : browsing ? 0.28 : duration,
            ease: [0.22, 0.72, 0.18, 1],
            delay: !reduced && !browsing && extraction === 'fan' ? 0.09 : 0,
          },
        }}
        variants={{
          returning: (exchange: boolean) => ({
            transform: reduced ? open : closed,
            opacity: reduced ? 0 : placement.storedOpacity,
            transition: {
              duration: reduced ? 0.06 : exchange ? 0.16 : 0.18,
              ease: [0.32, 0, 0.67, 0],
            },
          }),
        }}
        exit="returning"
        onAnimationComplete={() => setSettled(true)}
      >
        <div className="slot-card-material" aria-hidden="true">
          <i />
          <i />
          <SceneCardArt scene={scene} study={art} />
        </div>
        <div className="slot-card-content">
          <div className="elsewhere-preview-head">
            <span className="elsewhere-preview-icon" aria-hidden="true">
              <DockIcon name={link.label === 'GitHub' ? 'github' : 'journal'} />
            </span>
            <div>
              <span className="elsewhere-preview-kicker">Elsewhere</span>
              <strong>{link.label}</strong>
            </div>
            <a
              className="elsewhere-preview-arrow"
              href={link.href}
              aria-label={`Open ${link.label}`}
            >
              ↗
            </a>
          </div>
          <div className="elsewhere-preview-body">
            <p className="elsewhere-preview-identity">
              {link.preview?.identity}
            </p>
            {study !== 'glyph' && (
              <p className="elsewhere-preview-description">
                {link.preview?.description}
              </p>
            )}
          </div>
          {study === 'tile' && (
            <div
              className="elsewhere-preview-topics"
              style={{ maxWidth: placement.lowerWidth }}
            >
              {link.preview?.topics.map((topic) => (
                <span key={topic}>{topic}</span>
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
