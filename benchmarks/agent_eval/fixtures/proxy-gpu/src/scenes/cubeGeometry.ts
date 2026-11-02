import * as THREE from 'three';
import settings from '../content/scenes.json';
import { seededRandom } from './random';

export function createCubeGeometry(count: number, seedValue: number) {
  const baseGeometry = new THREE.BoxGeometry(1, 1, 1);
  const { random, range, pick } = seededRandom(seedValue);
  const colorToVec3 = (hex: string) => new THREE.Color(hex).toArray();
  const clusteredGpuX = (spread: number) => {
    if (random() > 0.72) return range(-spread * 1.18, spread * 1.18);
    const value = range(-1, 1);
    return (
      Math.sign(value) * Math.pow(Math.abs(value), 1.54) * spread * 0.92 +
      range(-1.1, 1.1)
    );
  };
  const gpuLayerRatios = { far: 0.38, foreground: 0.76 };
  const geometry = new THREE.InstancedBufferGeometry();
  geometry.index = baseGeometry.index;
  geometry.setAttribute('position', baseGeometry.getAttribute('position'));
  geometry.setAttribute('normal', baseGeometry.getAttribute('normal'));
  geometry.instanceCount = count;

  const offsets = new Float32Array(count * 3);
  const scales = new Float32Array(count * 3);
  const piles = new Float32Array(count * 3);
  const motions = new Float32Array(count * 4);
  const rotations = new Float32Array(count * 4);
  const tints = new Float32Array(count * 3);
  const accents = new Float32Array(count * 3);
  const alphas = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    const isFar = i < count * gpuLayerRatios.far;
    const isForeground = i > count * gpuLayerRatios.foreground;
    const xRange = isFar ? 34 : isForeground ? 24 : 25.5;
    const z = isFar
      ? range(-48, -22)
      : isForeground
        ? range(-13, -2.5)
        : range(-30, -7);
    const scaleBase = isFar
      ? range(0.34, 0.9)
      : isForeground
        ? range(0.95, 2.36)
        : range(0.72, 1.82);
    const tint = colorToVec3(
      pick(['#67edff', '#26cfff', '#00bffe', '#75f4ff', settings.cubes.cube]),
    );
    const accent = colorToVec3(
      pick([settings.cubes.highlight, '#d546dc', '#ff4b31', '#2347ff']),
    );
    const x = clusteredGpuX(xRange);

    offsets[i * 3] = x;
    offsets[i * 3 + 1] = 0;
    offsets[i * 3 + 2] = z;

    piles[i * 3] = x * range(0.62, 0.94) + range(-2.2, 2.2);
    piles[i * 3 + 1] = isFar
      ? range(2.2, 9.2)
      : isForeground
        ? range(0.2, 5.4)
        : range(0.8, 7.2);
    piles[i * 3 + 2] = isForeground ? range(-13, -3) : z + range(-2.4, 2.4);

    scales[i * 3] = scaleBase * range(0.78, 1.32);
    scales[i * 3 + 1] = scaleBase * range(0.78, 1.28);
    scales[i * 3 + 2] = scaleBase * range(0.78, 1.34);

    motions[i * 4] = isFar
      ? range(0.005, 0.013)
      : isForeground
        ? range(0.012, 0.028)
        : range(0.009, 0.02);
    motions[i * 4 + 1] = isFar ? range(0.08, 0.36) : range(0.1, 0.56);
    motions[i * 4 + 2] = range(0, Math.PI * 2);
    motions[i * 4 + 3] = random();

    rotations[i * 4] = range(-Math.PI, Math.PI);
    rotations[i * 4 + 1] = range(-Math.PI, Math.PI);
    rotations[i * 4 + 2] = range(-Math.PI, Math.PI);
    rotations[i * 4 + 3] = isFar ? range(-0.07, 0.07) : range(-0.2, 0.2);

    tints.set(tint, i * 3);
    accents.set(accent, i * 3);
    alphas[i] = isFar
      ? range(0.22, 0.44)
      : isForeground
        ? range(0.78, 0.98)
        : range(0.7, 0.94);
  }

  geometry.setAttribute(
    'instanceOffset',
    new THREE.InstancedBufferAttribute(offsets, 3),
  );
  geometry.setAttribute(
    'instanceScale',
    new THREE.InstancedBufferAttribute(scales, 3),
  );
  geometry.setAttribute(
    'instancePile',
    new THREE.InstancedBufferAttribute(piles, 3),
  );
  geometry.setAttribute(
    'instanceMotion',
    new THREE.InstancedBufferAttribute(motions, 4),
  );
  geometry.setAttribute(
    'instanceRotation',
    new THREE.InstancedBufferAttribute(rotations, 4),
  );
  geometry.setAttribute(
    'instanceTint',
    new THREE.InstancedBufferAttribute(tints, 3),
  );
  geometry.setAttribute(
    'instanceAccent',
    new THREE.InstancedBufferAttribute(accents, 3),
  );
  geometry.setAttribute(
    'instanceAlpha',
    new THREE.InstancedBufferAttribute(alphas, 1),
  );
  return geometry;
}
