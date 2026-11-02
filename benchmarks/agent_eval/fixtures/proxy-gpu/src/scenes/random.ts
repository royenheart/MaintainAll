export function seededRandom(initialSeed: number) {
  let seed = initialSeed;
  const random = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  const range = (min: number, max: number) => min + (max - min) * random();
  const pick = <T>(items: readonly T[]): T => {
    if (!items.length) throw new Error('Cannot pick from an empty collection');
    return items[Math.floor(random() * items.length)]!;
  };
  return { random, range, pick };
}
