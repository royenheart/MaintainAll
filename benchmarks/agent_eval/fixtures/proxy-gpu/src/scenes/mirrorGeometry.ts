import { BufferGeometry, Float32BufferAttribute } from 'three';

type Point = readonly [number, number];

// Clip the panel against the perpendicular bisector between two seeded sites.
function clipCell(polygon: Point[], site: Point, other: Point): Point[] {
  const nx = other[0] - site[0];
  const ny = other[1] - site[1];
  const boundary =
    (other[0] ** 2 + other[1] ** 2 - site[0] ** 2 - site[1] ** 2) / 2;
  const result: Point[] = [];
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i]!;
    const b = polygon[(i + 1) % polygon.length]!;
    const da = a[0] * nx + a[1] * ny - boundary;
    const db = b[0] * nx + b[1] * ny - boundary;
    if (da <= 0) result.push(a);
    if (da <= 0 !== db <= 0) {
      const t = da / (da - db);
      result.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
  }
  return result;
}

export function createMirrorGeometry(seed: number, aspect: number) {
  let state = seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
  const sites: Point[] = [];
  const phases: number[] = [];
  // Stable site identities across resize; aspect changes the metric, not the seed.
  for (let row = 0; row < 5; row++) {
    for (let column = 0; column < 7; column++) {
      sites.push([
        (((column + 0.18 + random() * 0.64) / 7) * 2 - 1) * aspect,
        ((row + 0.18 + random() * 0.64) / 5) * 2 - 1,
      ]);
      phases.push(random());
    }
  }
  const positions: number[] = [];
  const centers: number[] = [];
  const seeds: number[] = [];
  const edges: number[] = [];
  const cells: Point[][] = [];
  sites.forEach((site, index) => {
    let cell: Point[] = [
      [-aspect, -1],
      [aspect, -1],
      [aspect, 1],
      [-aspect, 1],
    ];
    sites.forEach((other, otherIndex) => {
      if (index !== otherIndex && cell.length)
        cell = clipCell(cell, site, other);
    });
    cells.push(cell);
    for (let i = 0; i < cell.length; i++) {
      const triangle = [site, cell[i]!, cell[(i + 1) % cell.length]!];
      triangle.forEach((point, corner) => {
        positions.push(point[0] / aspect, point[1], 0);
        centers.push(site[0] / aspect, site[1]);
        seeds.push(phases[index]!);
        // Fan interpolation marks only the polygon perimeter, not internal spokes.
        edges.push(corner === 0 ? 1 : 0);
      });
    }
  });
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('aCenter', new Float32BufferAttribute(centers, 2));
  geometry.setAttribute('aSeed', new Float32BufferAttribute(seeds, 1));
  geometry.setAttribute('aEdge', new Float32BufferAttribute(edges, 1));
  geometry.userData.cellCount = cells.length;
  return geometry;
}
