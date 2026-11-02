import { useState } from 'react';
import { slotCardSamples } from '../explorations/orbit/slot-card-fixtures';
import { OrbitStudy } from '../explorations/orbit/OrbitStudy';
import type { RailStudy } from '../explorations/orbit/ElsewhereRails';
import {
  parseCardFinish,
  parseSurfaceMotion,
  parseElsewhereStudy,
  parseCardExtraction,
  parseCardMaterial,
  parseCardArtStudy,
  parseElsewhereMark,
} from '../explorations/orbit/card-finishes';
import type {
  CoverSelection,
  IdentityStudy,
  DetailStudy,
} from '../explorations/orbit/presentation';

export function OrbitPreview() {
  const [options] = useState(() => new URLSearchParams(window.location.search));
  const scene = options.get('scene');
  const cover = options.get('cover');
  const identity = options.get('identity');
  const details = options.get('details');
  const rails = options.get('rails');
  return (
    <>
      <OrbitStudy
        interfaceMode="continuous"
        fontStudy="plex"
        cardFinish={parseCardFinish(options.get('finish'))}
        surfaceMotion={parseSurfaceMotion(options.get('surface'))}
        elsewhereStudy={parseElsewhereStudy(options.get('elsewhere'))}
        elsewhereLinks={
          options.get('cards') === 'demo' ? slotCardSamples : undefined
        }
        cardExtraction={parseCardExtraction(options.get('cardMotion'))}
        cardMaterial={parseCardMaterial(options.get('cardSurface'))}
        cardArt={parseCardArtStudy(options.get('cardArt'))}
        elsewhereMark={parseElsewhereMark(options.get('marks'))}
        initialCard={
          options.get('card') === 'elsewhere'
            ? 'elsewhere'
            : options.get('card') === 'next'
              ? 'next'
              : 'identity'
        }
        railStudy={
          (['glide', 'tether', 'relay'].includes(rails ?? '')
            ? rails
            : 'glide') as RailStudy
        }
        detailStudy={
          (['etch', 'flow', 'orbit'].includes(details ?? '')
            ? details
            : 'flow') as DetailStudy
        }
        coverStudy={
          (['ripple', 'frost', 'meniscus'].includes(cover ?? '')
            ? cover
            : 'random') as CoverSelection
        }
        identityStudy={
          (['orbit', 'badge', 'route'].includes(identity ?? '')
            ? identity
            : 'orbit') as IdentityStudy
        }
        initialScene={
          scene === 'cubes' || scene === 'horizon' ? scene : undefined
        }
        skipEntrance={options.get('skipIntro') === '1'}
        graphics={options.get('graphics') === 'poster' ? 'poster' : 'auto'}
      />
    </>
  );
}
