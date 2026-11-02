import { DataTexture, FloatType, NearestFilter, RGFormat } from 'three';
import manifest from './manifest.json';
import { decodeTable, OPTICAL_VERSION, TABLE_SIZES } from './optics';

export interface OpticalTextures {
  deflection: DataTexture;
  inverseRadius: DataTexture;
  dispose(): void;
}

export async function loadOpticalTextures(
  signal: AbortSignal,
): Promise<OpticalTextures> {
  if (manifest.version !== OPTICAL_VERSION)
    throw new Error('Incompatible optical tables');
  const decoded = await Promise.all(
    (['deflection', 'inverseRadius'] as const).map(async (kind) => {
      const asset = manifest.files[kind];
      const response = await fetch(
        `${import.meta.env.BASE_URL}optics/${asset.file}?v=${asset.sha256}`,
        { signal },
      );
      if (!response.ok)
        throw new Error(`Optical asset request failed: ${response.status}`);
      const buffer = await response.arrayBuffer();
      if (globalThis.crypto?.subtle) {
        const digest = await crypto.subtle.digest('SHA-256', buffer);
        const hash = Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, '0'),
        ).join('');
        if (hash !== asset.sha256)
          throw new Error('Optical asset checksum mismatch');
      }
      return decodeTable(buffer, TABLE_SIZES[kind]);
    }),
  );
  signal.throwIfAborted();
  const textures = decoded.map(({ data, width, height }) => {
    const texture = new DataTexture(data, width, height, RGFormat, FloatType);
    // The shader performs bilinear interpolation; no float-linear extension is required.
    texture.minFilter = NearestFilter;
    texture.magFilter = NearestFilter;
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    return texture;
  });
  return {
    deflection: textures[0]!,
    inverseRadius: textures[1]!,
    dispose: () => textures.forEach((texture) => texture.dispose()),
  };
}
