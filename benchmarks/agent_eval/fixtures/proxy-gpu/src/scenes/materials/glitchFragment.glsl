uniform sampler2D uSource;
uniform float uTransition;
uniform float uFractureOverride;
uniform float uAspect;
uniform float uViewHeight;
uniform vec2 uCenter;
uniform float uSeed;
uniform int uDiagnostic;
varying vec2 vUv;
varying float vShardEdge;
varying float vShardSeed;
varying float vShardOpacity;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7)) + uSeed * 0.013) * 43758.5453);
}
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1,0)), f.x),
             mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
}
vec3 sampleSource(vec2 uv) {
  // Outside the source is empty space, not a repeated screen-edge streak.
  float inside = step(0.0, uv.x) * step(uv.x, 1.0) * step(0.0, uv.y) * step(uv.y, 1.0);
  return texture2D(uSource, clamp(uv, vec2(0.001), vec2(0.999))).rgb * inside;
}
void main() {
  float q = 1.0 - uTransition;
  vec2 metric = vec2(uAspect, 1.0) * uViewHeight;
  vec2 p = (vUv - uCenter) * metric;
  vec2 origin = vec2(-1.8, 1.7);
  // A static irregular arrival field grows monotonically; it cannot retreat or pop.
  float distanceField = length((p - origin) * vec2(0.84, 1.0));
  distanceField += (noise(p * 1.8) - 0.5) * 0.70;
  distanceField += (noise(floor(p * vec2(4.0, 9.0))) - 0.5) * 0.22;
  float reach = mix(-0.45, length(metric) * 1.15, smoothstep(0.02, 0.60, q));
  float infected = 1.0 - smoothstep(reach - 0.25, reach + 0.32, distanceField);
  infected *= smoothstep(0.01, 0.09, q);
  if (uDiagnostic == 1) { gl_FragColor = vec4(vec3(infected), 1.0); return; }

  float instability = smoothstep(0.16, 0.66, q) * infected;
  float clock = q * 16.0;
  // Coarse, temporally coherent displacement moves the void, disk and sky together.
  vec2 field = vec2(noise(p * 0.55 + vec2(clock * 0.22, 0.0)),
                    noise(p.yx * 0.67 + vec2(3.7, -clock * 0.16))) - 0.5;
  vec2 warp = field * instability * 1.55;
  warp.x += sin(p.y * 2.4 + clock * 0.7) * instability * 0.20;
  warp.y += sin(p.x * 1.5 - clock * 0.8) * instability * 0.18;
  // Scanline blocks shear the actual source; they carry no independent emission.
  float band = floor(p.y * 7.0);
  float block = noise(vec2(band, floor(clock * 0.7)));
  float tear = smoothstep(0.64, 0.88, block) * (hash(vec2(band, 4.1)) - 0.5);
  warp.x += tear * instability * 0.85;
  vec2 uv = vUv + warp / metric;
  uv += vec2(vShardSeed - 0.5, sin(vShardSeed * 21.0) * 0.35)
        * smoothstep(0.05, 0.26, uFractureOverride) * 0.42 / metric;
  float blurEnvelope = smoothstep(0.29, 0.66, q) * infected;
  float blurAmount = uDiagnostic == 2 ? 0.0 : blurEnvelope;
  vec2 axis = normalize(vec2(0.75, 1.0 + field.y * 0.6));
  vec2 smear = axis * blurAmount * 0.24 / metric;
  vec3 color = vec3(0.0);
  // Nine bounded texture fetches, not nine expensive evaluations of the scene.
  for (int i = -4; i <= 4; i++) {
    float t = float(i) / 4.0;
    float weight = exp(-t * t * 2.0);
    color += sampleSource(uv + smear * t) * weight;
  }
  color /= 4.8980306;
  vec2 split = vec2(0.018 + instability * 0.050, 0.010) * infected / metric;
  vec3 channels = vec3(sampleSource(uv + split).r, color.g, sampleSource(uv - split).b);
  color = mix(color, channels, infected * 0.40 * (1.0 - blurEnvelope * 0.55));
  // Gold turns locally to cyan/iris. Luminance still comes from scene material.
  float colorBlocks = 0.65 + noise(floor(p * vec2(2.3, 6.5))) * 0.35;
  vec3 displacedColor = mix(color.brg * vec3(0.55, 1.0, 1.22),
                            color.gbr * vec3(0.90, 0.62, 1.12), noise(p * 0.7));
  color = mix(color, displacedColor, infected * colorBlocks * 0.79);
  float edge = 1.0 - smoothstep(0.0, max(fwidth(vShardEdge) * 1.25, 0.003), vShardEdge);
  float glint = smoothstep(0.02, 0.17, uFractureOverride)
                * (1.0 - smoothstep(0.50, 0.80, uFractureOverride));
  color += vec3(0.28, 0.38, 0.42) * edge * glint;
  gl_FragColor = vec4(color, vShardOpacity);
}
