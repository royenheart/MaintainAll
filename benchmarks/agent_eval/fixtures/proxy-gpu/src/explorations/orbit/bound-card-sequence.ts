/** Up to three physical cards, ordered from the lower-left front to upper-right rear. */
export function cardWindow(index: number, count: number): number[] {
  if (count < 1) return [];
  return Array.from(
    { length: Math.min(3, count) },
    (_, offset) => (((index + offset) % count) + count) % count,
  );
}
export function stepBoundCard(
  index: number,
  delta: number,
  count: number,
): number {
  return count ? (((index + Math.sign(delta)) % count) + count) % count : 0;
}
