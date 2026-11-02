import * as THREE from 'three';
import settings from '../../content/scenes.json';

const goldenAccretionPalette = {
  deepOrange: new THREE.Color(settings.horizon.deepOrange),
  richGold: new THREE.Color(settings.horizon.gold),
  paleGold: new THREE.Color(settings.horizon.paleGold),
  whiteGold: new THREE.Color(settings.horizon.whiteGold),
};

export function eventHorizonBackdropMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPresence: { value: 1 },
      uSceneAspectRatio: { value: 1 },
      uDeepOrange: { value: goldenAccretionPalette.deepOrange },
      uGold: { value: goldenAccretionPalette.richGold },
    },
    vertexShader: `
            varying vec2 vUv;

            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
    fragmentShader: `
            precision mediump float;

            uniform float uTime;
            uniform float uPresence;
            uniform float uSceneAspectRatio;
            uniform vec3 uDeepOrange;
            uniform vec3 uGold;
            varying vec2 vUv;

            void main() {
                vec2 p = vUv - 0.5;
                p.x *= uSceneAspectRatio;
                float upperWarmth = smoothstep(0.1, 0.88, vUv.y);
                float centerField = 1.0 - smoothstep(0.0, 0.95, length(p));
                float lowerVignette = 1.0 - smoothstep(0.04, 0.58, vUv.y);
                float softBand = exp(-pow((vUv.y - 0.72) * 2.7, 2.0));
                float shimmer = 0.5 + 0.5 * sin(uTime * 0.22 + p.x * 2.4);
                vec3 base = vec3(0.012, 0.004, 0.0);
                vec3 color = mix(base, uDeepOrange * 0.32, upperWarmth * 0.42 + centerField * 0.18);
                color = mix(color, uGold * 0.22, softBand * 0.16 + shimmer * centerField * 0.035);
                color = mix(color, base * 0.54, lowerVignette * 0.56);
                gl_FragColor = vec4(color, uPresence);
            }
        `,
    depthWrite: false,
    depthTest: false,
    transparent: true,
    side: THREE.DoubleSide,
  });
}

export function eventHorizonGlowMaterial({
  opacity = 1,
  intensity = 1,
  haloSpread = 1,
}: {
  opacity?: number;
  intensity?: number;
  haloSpread?: number;
}) {
  const eventHorizonRimPower = 1.24;
  const directGlowBoost = 1.68;
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPresence: { value: 1 },
      uOpacity: { value: opacity },
      uIntensity: { value: intensity },
      uHaloSpread: { value: haloSpread },
      uDirectGlowBoost: { value: directGlowBoost },
      uEventHorizonRimPower: { value: eventHorizonRimPower },
      uDeepOrange: { value: goldenAccretionPalette.deepOrange },
      uGold: { value: goldenAccretionPalette.richGold },
      uPaleGold: { value: goldenAccretionPalette.paleGold },
      uWhiteGold: { value: goldenAccretionPalette.whiteGold },
    },
    vertexShader: `
            varying vec2 vUv;

            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
    fragmentShader: `
            precision mediump float;

            uniform float uTime;
            uniform float uPresence;
            uniform float uOpacity;
            uniform float uIntensity;
            uniform float uHaloSpread;
            uniform float uDirectGlowBoost;
            uniform float uEventHorizonRimPower;
            uniform vec3 uDeepOrange;
            uniform vec3 uGold;
            uniform vec3 uPaleGold;
            uniform vec3 uWhiteGold;

            varying vec2 vUv;

            void main() {
                vec2 p = (vUv - 0.5) * vec2(1.48, 1.48);
                p.y += 0.035;
                float d = length(p);
                float angle = atan(p.y, p.x);

                float sideLift = smoothstep(0.34, 0.62, abs(p.x));
                float upperLift = smoothstep(-0.16, 0.34, p.y);
                float sideContactBridge = sideLift * (1.0 - smoothstep(0.08, 0.34, abs(p.y)));
                float haloArcMask = max(smoothstep(-0.12, 0.08, p.y), sideContactBridge);
                float continuousUpperHalo = haloArcMask * (1.0 - smoothstep(0.68, 0.75, d));
                float lowerGlowOcclusion = continuousUpperHalo;
                float lowerDimming = mix(0.28, 1.0, max(upperLift, sideLift * 0.74));
                float eventHorizonRim = exp(-pow((d - 0.502) * 24.0, 2.0));
                float paleInnerRim = exp(-pow((d - 0.49) * 36.0, 2.0)) * (upperLift * 0.82 + sideLift * 0.38);
                float whiteCrest = exp(-pow((d - 0.507) * 30.0, 2.0)) * (upperLift * 0.9 + sideLift * 0.42);
                float goldenField = exp(-pow((d - 0.58) * (7.4 / uHaloSpread), 2.0));
                float deepOrangeField = exp(-pow((d - 0.65) * (5.8 / uHaloSpread), 2.0));
                float hotStreak = pow(0.5 + 0.5 * sin(angle * 15.0 + d * 24.0 - uTime * 0.42), 9.0);
                float shimmer = 0.9 + 0.1 * sin(uTime * 0.62 + angle * 4.0);

                float rim = pow(eventHorizonRim, uEventHorizonRimPower);
                float alpha = (
                    rim * 1.32 +
                    paleInnerRim * 1.08 +
                    whiteCrest * 0.92 +
                    goldenField * 0.42 +
                    deepOrangeField * 0.2 +
                    hotStreak * rim * 0.18
                ) * lowerDimming * lowerGlowOcclusion * uOpacity * shimmer;
                alpha *= 1.0 - smoothstep(0.64, 0.78, d);
                alpha *= min(uDirectGlowBoost, 2.2);

                vec3 color = mix(uDeepOrange, uGold, smoothstep(0.49, 0.64, d));
                color = mix(color, uPaleGold, clamp(rim * 0.56 + paleInnerRim * 0.72 + whiteCrest * 0.32, 0.0, 1.0));
                color = mix(color, uWhiteGold, clamp(whiteCrest * 0.78 + paleInnerRim * 0.28 + hotStreak * rim * 0.18, 0.0, 1.0));
                gl_FragColor = vec4(color * uIntensity * uDirectGlowBoost, alpha * uPresence);
            }
        `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
}

export function eventHorizonCoreMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPresence: { value: 1 },
    },
    vertexShader: `
            varying vec2 vUv;

            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
    fragmentShader: `
            precision mediump float;

            uniform float uTime;
            uniform float uPresence;
            varying vec2 vUv;

            void main() {
                vec2 p = (vUv - 0.5) * vec2(1.14, 1.14);
                p.y += 0.02;
                float d = length(p);
                float sphereSilhouette = 1.0 - smoothstep(0.492, 0.526, d);
                float rimSoftBlend = smoothstep(0.44, 0.506, d) * (1.0 - smoothstep(0.506, 0.538, d));
                float edge = smoothstep(0.36, 0.505, d);
                float upperFalloff = smoothstep(-0.42, 0.36, p.y);
                float barelyVisibleSurface = 0.035 * edge * upperFalloff;
                barelyVisibleSurface += 0.01 * sin((p.x + p.y) * 18.0 + uTime * 0.2) * edge;
                float horizonContactGlow = rimSoftBlend * upperFalloff;
                vec3 coreColor = mix(vec3(0.0, 0.0, 0.0), vec3(0.04, 0.024, 0.008), barelyVisibleSurface);
                coreColor = mix(coreColor, vec3(0.075, 0.038, 0.008), horizonContactGlow * 0.18);
                gl_FragColor = vec4(coreColor, sphereSilhouette * uPresence);
            }
        `,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
}

export function eventHorizonDiskMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPresence: { value: 1 },
      uSceneAspectRatio: { value: 1 },
      uDeepOrange: { value: goldenAccretionPalette.deepOrange },
      uGold: { value: goldenAccretionPalette.richGold },
      uPaleGold: { value: goldenAccretionPalette.paleGold },
      uWhiteGold: { value: goldenAccretionPalette.whiteGold },
    },
    vertexShader: `
            varying vec2 vUv;

            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
    fragmentShader: `
            precision mediump float;

            uniform float uTime;
            uniform float uPresence;
            uniform float uSceneAspectRatio;
            uniform vec3 uDeepOrange;
            uniform vec3 uGold;
            uniform vec3 uPaleGold;
            uniform vec3 uWhiteGold;
            varying vec2 vUv;

            void main() {
                vec2 p = vUv - 0.5;
                p.x *= mix(1.7, 2.4, smoothstep(1.0, 2.0, uSceneAspectRatio));
                p.y = (p.y + 0.16) * 2.55;

                float diskPerspective = smoothstep(-0.42, 0.72, p.y);
                float edgeSpread = 1.0 - smoothstep(0.72, 1.28, abs(p.x));
                float lowerFade = 1.0 - smoothstep(0.9, 1.22, p.y);
                float foregroundExtent = smoothstep(-0.98, -0.62, p.y);

                float ellipseRadius = length(vec2(p.x * 0.68, p.y * 2.8));
                float accretionDiskRings = 0.0;
                accretionDiskRings += exp(-pow((ellipseRadius - 0.58) * 34.0, 2.0)) * 0.62;
                accretionDiskRings += exp(-pow((ellipseRadius - 0.76) * 42.0, 2.0)) * 0.5;
                accretionDiskRings += exp(-pow((ellipseRadius - 0.96) * 48.0, 2.0)) * 0.46;
                accretionDiskRings += exp(-pow((ellipseRadius - 1.18) * 54.0, 2.0)) * 0.38;
                accretionDiskRings += exp(-pow((ellipseRadius - 1.42) * 66.0, 2.0)) * 0.26;

                float fineBands = pow(0.5 + 0.5 * sin(ellipseRadius * 58.0 - uTime * 0.42 + p.x * 1.2), 12.0);
                float perspectiveY = clamp((p.y + 0.94) / 1.82, 0.0, 1.0);
                float foregroundAccretionRings = pow(
                    0.5 + 0.5 * sin(
                        p.y * (36.0 + perspectiveY * 46.0) +
                        p.x * p.x * 0.9 -
                        uTime * 0.22
                    ),
                    16.0
                );
                float centerDarkMask = 1.0 - smoothstep(0.46, 0.78, length(vec2(p.x * 0.88, p.y * 1.52)));
                float innerShadow = 1.0 - centerDarkMask * 0.72;
                float longHorizon = exp(-pow((p.y + 0.04) * 28.0, 2.0)) * (0.28 + edgeSpread * 0.72);
                float warmSheet = exp(-pow((p.y - 0.12) * 2.2, 2.0)) * (0.35 + edgeSpread * 0.5);
                float nearFieldDiskBody = smoothstep(-0.74, 0.08, p.y) * (1.0 - smoothstep(0.82, 1.14, p.y));
                float foregroundDiskOcclusion = smoothstep(-0.24, 0.2, p.y) * (1.0 - smoothstep(0.78, 1.12, p.y));
                float diskOcclusionAlpha = max(foregroundDiskOcclusion * 0.88, nearFieldDiskBody * 0.36) * edgeSpread * lowerFade;
                float foregroundRingAlpha = foregroundAccretionRings * edgeSpread * lowerFade * foregroundExtent * 0.28;
                float ringAlpha = (
                    accretionDiskRings * 0.58 +
                    fineBands * 0.14 +
                    foregroundRingAlpha +
                    longHorizon * 0.42 +
                    warmSheet * 0.24
                ) * edgeSpread * lowerFade * innerShadow;
                float alpha = max(diskOcclusionAlpha, ringAlpha);

                vec3 darkDisk = vec3(0.026, 0.006, 0.0);
                vec3 color = mix(darkDisk, uDeepOrange * 0.58, warmSheet * 0.34 + accretionDiskRings * 0.18 + nearFieldDiskBody * 0.08);
                color = mix(color, uGold, clamp(accretionDiskRings * 0.62 + longHorizon * 0.34 + foregroundAccretionRings * foregroundExtent * 0.12, 0.0, 1.0));
                color = mix(color, uPaleGold, clamp(longHorizon * 0.38 + fineBands * 0.14 + foregroundAccretionRings * foregroundExtent * 0.04, 0.0, 1.0));
                color = mix(color, uWhiteGold, clamp(longHorizon * 0.08, 0.0, 0.24));
                gl_FragColor = vec4(color, alpha * uPresence);
            }
        `,
    transparent: true,
    blending: THREE.NormalBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
}
