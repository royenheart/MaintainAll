uniform bool uMirrorRupture;
uniform float uFractureOverride;
uniform bool uExpressive;
uniform float uTransition;
uniform float uDirection;
uniform float uAspect;
uniform float uViewHeight;
uniform vec2 uCenter;
attribute vec2 aCenter;
attribute float aSeed;
attribute float aEdge;
varying vec2 vUv;
varying float vShardEdge;
varying float vShardSeed;
varying float vShardOpacity;

mat2 mirrorRotation(float angle) {
  float c = cos(angle), s = sin(angle);
  return mat2(c, -s, s, c);
}
void main() {
  vUv = position.xy * 0.5 + 0.5;
  vShardEdge = aEdge;
  vShardSeed = aSeed;
  vShardOpacity = 1.0;
  gl_Position = vec4(position.xy, 1.0, 1.0);
  if (!uMirrorRupture || !uExpressive || uDirection >= 0.0) return;
  float q = uFractureOverride >= 0.0 ? uFractureOverride : 1.0 - uTransition;
  vec2 metric = vec2(uAspect, 1.0) * uViewHeight;
  vec2 center = (aCenter * 0.5 + 0.5 - uCenter) * metric;
  vec2 local = (position.xy - aCenter) * 0.5 * metric;
  float tension = smoothstep(0.05, 0.24, q);
  float release = smoothstep(0.25 + aSeed * 0.08, 0.90, q);
  float angle = (aSeed - 0.5) * (tension * 0.18 + release * 1.1);
  local = mirrorRotation(angle) * local;
  float tilt = (aSeed - 0.5) * (tension * 0.24 + release * 1.9);
  float depth = local.x * sin(tilt);
  local.x *= cos(tilt);
  local *= 1.0 - release * 0.30;
  vec2 outward = normalize(center + vec2(0.01));
  center += outward * release * (1.8 + aSeed * 3.8);
  center.y += release * sin(aSeed * 31.0) * 0.7;
  vec2 point = center + local;
  vec2 clip = (point / metric + uCenter) * 2.0 - 1.0;
  // A changing plane normal gives real panel foreshortening and perspective.
  float w = max(0.65, 1.0 + depth * 0.075 + release * (aSeed - 0.5) * 0.28);
  gl_Position = vec4(clip, 0.0, w);
  vShardOpacity = 1.0 - smoothstep(0.56 + aSeed * 0.13, 0.78 + aSeed * 0.18, q);
}
