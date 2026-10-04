import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

// Register this example in an existing project; dimensions/fps belong to its Composition.
export const CreativeStudy = ({title = 'One clear moment', entranceSeconds = 0.8,
  mechanism = 'travel', accent = '#b25543'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(1, entranceSeconds * fps)], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const transform = mechanism === 'focus' ? `scale(${0.7 + 0.3 * progress})`
    : mechanism === 'travel' ? `translateX(${-100 * (1 - progress)}px)` : 'none';
  return React.createElement(AbsoluteFill, {
    style: {background: '#f4f1e9', alignItems: 'center', justifyContent: 'center'},
  }, React.createElement('div', {
    style: {fontFamily: 'sans-serif', fontSize: 64, padding: 80, background: accent,
      color: 'white', opacity: mechanism === 'reveal' ? 1 : progress, transform,
      clipPath: mechanism === 'reveal' ? `inset(0 ${100 * (1 - progress)}% 0 0)` : 'none'},
  }, title));
};
