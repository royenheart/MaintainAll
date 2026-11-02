import { motion } from 'motion/react';
import { rotaryDesigns, type RotaryDesign } from './rotary-designs';

export function WheelTrim({
  design,
  index,
  duration,
  reduced,
}: {
  design: RotaryDesign;
  index: number;
  duration: number;
  reduced: boolean;
}) {
  return (
    <motion.svg
      className="rotary-wheel-trim"
      viewBox="0 0 200 200"
      aria-hidden="true"
      animate={{ rotate: -index * rotaryDesigns[design].step }}
      transition={{
        duration: reduced ? 0 : duration,
        ease: [0.22, 0.72, 0.18, 1],
      }}
    >
      {design === 'tangent' &&
        [0, 90, 180, 270].map((angle) => (
          <path
            key={angle}
            transform={`rotate(${angle} 100 100)`}
            d="M38 38A88 88 0 0 1 123 15"
          />
        ))}
      {design === 'drum' && (
        <>
          <circle cx="100" cy="100" r="92" />
          {Array.from({ length: 8 }, (_, i) => (
            <circle
              key={i}
              cx="100"
              cy="9"
              r="3"
              transform={`rotate(${i * 45} 100 100)`}
            />
          ))}
        </>
      )}
      {design === 'orbit' && (
        <>
          <ellipse
            cx="100"
            cy="100"
            rx="96"
            ry="86"
            transform="rotate(-28 100 100)"
          />
          <path d="M158 24A94 94 0 0 1 194 100" />
        </>
      )}
    </motion.svg>
  );
}
